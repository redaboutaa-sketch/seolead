"""Pre-publication SEO crawl — the site judged as a crawler would judge it.

Crawls a LOCAL stack over HTTP (BFS from `/`, same-origin, plus robots.txt,
sitemap.xml and llms.txt), and writes a route-by-route markdown table plus a
findings list. It changes nothing anywhere: it is a reader.

Two runs make the pre-publication picture:

    # 1. The stack as configured today (staging: true, noindex)
    python tools/seo_precrawl.py --base http://127.0.0.1:3100 \
        --out docs/release/PRECRAWL_STAGING.md --label "staging (config réelle)"

    # 2. The same stack relaunched against a COPY of the config with
    #    staging: false — SEOLEAD_SITE_CONFIG_DIR points the API at the copy;
    #    allow_indexing stays false, so nothing becomes indexable anywhere.
    python tools/seo_precrawl.py --base http://127.0.0.1:3100 \
        --out docs/release/PRECRAWL_ASIF.md --label "simulation publication"

Checks per route: HTTP status and redirect chain, <title>, meta description,
H1s, robots meta + X-Robots-Tag, canonical, JSON-LD validity and @types,
Open Graph and twitter tags, outgoing internal links, no-JS text volume
(the crawler reads the served HTML — what it sees is what exists without a
browser). Site-wide: broken internal links, duplicated titles/descriptions,
sitemap-vs-crawl orphans, trailing-slash duplication.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


class _PageStrict(HTMLParser):
    """One served document, reduced to what a crawler indexes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.h1s: list[str] = []
        self.hrefs: list[str] = []
        self.jsonld_raw: list[str] = []
        self.text_chars = 0
        self._stack: list[str] = []
        self._in_jsonld = False
        self._h1_open = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._stack.append(tag)
        if tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self.jsonld_raw.append("")
        elif tag == "h1":
            self._h1_open = True
            self.h1s.append("")

    def handle_endtag(self, tag):
        while self._stack and self._stack.pop() != tag:
            pass
        if tag == "script":
            self._in_jsonld = False
        elif tag == "h1":
            self._h1_open = False

    def handle_data(self, data):
        if self._in_jsonld:
            self.jsonld_raw[-1] += data
            return
        # <title> inside <svg> is an accessibility label, not the document
        # title — the homepage hero taught the first version the difference.
        if "title" in self._stack and "svg" not in self._stack:
            self.title += data
        if self._h1_open and self.h1s:
            self.h1s[-1] += data
        if self._stack and self._stack[-1] not in ("script", "style"):
            self.text_chars += len(data.strip())


@dataclass
class RouteReport:
    path: str
    status: int = 0
    redirect_to: str | None = None
    title: str = ""
    description: str = ""
    canonical: str = ""
    robots_meta: str = ""
    robots_header: str = ""
    h1s: list[str] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)
    jsonld_errors: list[str] = field(default_factory=list)
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    internal_links: list[str] = field(default_factory=list)
    text_chars: int = 0
    content_type: str = ""


def _meta(metas: list[dict], **want) -> str:
    for m in metas:
        if all(m.get(k, "").lower() == v.lower() for k, v in want.items()):
            return m.get("content", "")
    return ""


def _jsonld_types(node, out: list[str]) -> None:
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(str(x) for x in t)
        for v in node.values():
            _jsonld_types(v, out)
    elif isinstance(node, list):
        for v in node:
            _jsonld_types(v, out)


def crawl(base: str, probes: list[str] | None = None
          ) -> tuple[dict[str, RouteReport], dict]:
    client = httpx.Client(base_url=base, follow_redirects=False, timeout=20)
    # Probes: routes to judge even when nothing links to them — a gated page
    # whose correct state is 404 still belongs in the table.
    seeds = ["/", "/robots.txt", "/sitemap.xml", "/llms.txt"] + (probes or [])

    sitemap_paths: list[str] = []
    try:
        sm = client.get("/sitemap.xml")
        if sm.status_code == 200:
            sitemap_paths = [urlsplit(u).path or "/"
                             for u in re.findall(r"<loc>([^<]+)</loc>", sm.text)]
    except httpx.HTTPError:
        pass

    queue = list(dict.fromkeys(seeds + sitemap_paths))
    seen: dict[str, RouteReport] = {}
    linked_from: dict[str, set[str]] = {}

    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        report = RouteReport(path=path)
        seen[path] = report
        try:
            resp = client.get(path)
        except httpx.HTTPError as exc:
            report.status = -1
            report.title = f"(erreur transport: {exc.__class__.__name__})"
            continue
        report.status = resp.status_code
        report.robots_header = resp.headers.get("x-robots-tag", "")
        report.content_type = resp.headers.get("content-type", "").split(";")[0]
        if resp.status_code in (301, 302, 307, 308):
            report.redirect_to = resp.headers.get("location", "")
            target = urlsplit(urljoin(path, report.redirect_to)).path or "/"
            if target not in seen:
                queue.append(target)
            continue
        if "html" not in report.content_type:
            report.text_chars = len(resp.content)
            continue

        page = _PageStrict()
        page.feed(resp.text)
        report.title = page.title.strip()
        report.description = _meta(page.metas, name="description")
        report.robots_meta = _meta(page.metas, name="robots")
        report.h1s = [h.strip() for h in page.h1s if h.strip()]
        report.text_chars = page.text_chars
        report.og = {m["property"]: m.get("content", "") for m in page.metas
                     if m.get("property", "").startswith("og:")}
        report.twitter = {m["name"]: m.get("content", "") for m in page.metas
                         if m.get("name", "").startswith("twitter:")}
        for link in page.links:
            if link.get("rel", "").lower() == "canonical":
                report.canonical = link.get("href", "")
        for raw in page.jsonld_raw:
            try:
                types: list[str] = []
                _jsonld_types(json.loads(raw), types)
                report.jsonld_types.extend(types)
            except json.JSONDecodeError as exc:
                report.jsonld_errors.append(str(exc))

        origin = urlsplit(base)
        for href in page.hrefs:
            parts = urlsplit(urljoin(base + path, href))
            # tel:, mailto: and friends are not routes.
            if parts.scheme not in ("", "http", "https"):
                continue
            if parts.netloc and parts.netloc != origin.netloc:
                continue
            target = parts.path or "/"
            report.internal_links.append(target)
            linked_from.setdefault(target, set()).add(path)
            if target not in seen and target not in queue:
                queue.append(target)

    # ── Site-wide findings ───────────────────────────────────────────────────
    findings: list[str] = []
    html_pages = {p: r for p, r in seen.items()
                  if r.content_type == "text/html" and r.status == 200}

    for path, r in seen.items():
        if r.status not in (200, 301, 302, 307, 308, 404) and r.status != -1:
            findings.append(f"`{path}` répond {r.status}")
    broken = sorted({t for t, sources in linked_from.items()
                     if t in seen and seen[t].status in (404, 500, -1)})
    for t in broken:
        findings.append(
            f"lien interne cassé vers `{t}` (depuis "
            f"{', '.join(sorted(linked_from[t])[:3])}) → {seen[t].status}")

    by_title: dict[str, list[str]] = {}
    by_desc: dict[str, list[str]] = {}
    for path, r in html_pages.items():
        by_title.setdefault(r.title, []).append(path)
        by_desc.setdefault(r.description, []).append(path)
    for title, paths in by_title.items():
        if title and len(paths) > 1:
            findings.append(f"titre dupliqué « {title[:60]} » : "
                            f"{', '.join(sorted(paths))}")
    for desc, paths in by_desc.items():
        if desc and len(paths) > 1:
            findings.append(f"meta description dupliquée sur "
                            f"{', '.join(sorted(paths))}")

    for path, r in html_pages.items():
        if len(r.h1s) != 1:
            findings.append(f"`{path}` porte {len(r.h1s)} H1")
        if not r.description:
            findings.append(f"`{path}` sans meta description")
        if r.jsonld_errors:
            findings.append(f"`{path}` JSON-LD invalide : {r.jsonld_errors}")
        if r.text_chars < 400:
            findings.append(f"`{path}` contenu no-JS très mince "
                            f"({r.text_chars} caractères)")

    # Trailing slash: the non-canonical spelling of every HTML page must not
    # serve a second 200 copy.
    with httpx.Client(base_url=base, follow_redirects=False, timeout=20) as c2:
        for path in list(html_pages):
            if path == "/":
                continue
            twin = path + "/" if not path.endswith("/") else path.rstrip("/")
            if twin in seen:
                continue
            try:
                status = c2.get(twin).status_code
            except httpx.HTTPError:
                continue
            if status == 200:
                findings.append(
                    f"duplication trailing slash : `{path}` ET `{twin}` "
                    f"servent 200")

    in_sitemap = set(sitemap_paths)
    crawl_reachable = set(linked_from) | {"/"}
    for path in sorted(in_sitemap - crawl_reachable):
        findings.append(f"orphelin : `{path}` est dans le sitemap mais "
                        f"aucun lien interne n'y mène")
    for path, r in html_pages.items():
        if path not in in_sitemap and "noindex" not in (
                r.robots_meta + r.robots_header).lower():
            findings.append(f"`{path}` indexable mais absent du sitemap")

    meta = {"sitemap_paths": sitemap_paths, "findings": findings,
            "linked_from": {k: sorted(v) for k, v in linked_from.items()}}
    client.close()
    return seen, meta


def render(seen: dict[str, RouteReport], meta: dict, label: str) -> str:
    lines = [
        f"### Crawl — {label}",
        "",
        "| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | "
        "JSON-LD | OG | Liens int. | Texte no-JS |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for path in sorted(seen):
        r = seen[path]
        if r.status in (301, 302, 307, 308):
            lines.append(f"| `{path}` | {r.status} → `{r.redirect_to}` "
                         f"| | | | | | | | | |")
            continue
        if r.content_type and "html" not in r.content_type:
            lines.append(f"| `{path}` | {r.status} | {r.robots_header or '—'} "
                         f"| | ({r.content_type}) | | | | | | {r.text_chars} o |")
            continue
        robots = r.robots_meta or r.robots_header or "—"
        og = "✓" if r.og.get("og:title") else "—"
        jsonld = ", ".join(sorted(set(r.jsonld_types))) or "—"
        lines.append(
            f"| `{path}` | {r.status} | {robots} | {r.canonical or '—'} "
            f"| {r.title[:50] or '—'} | {'✓' if r.description else '—'} "
            f"| {len(r.h1s)} | {jsonld} | {og} "
            f"| {len(set(r.internal_links))} | {r.text_chars} c |")
    lines += ["", f"**Constats ({len(meta['findings'])})**", ""]
    lines += [f"- {f}" for f in meta["findings"]] or ["- aucun"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="crawl")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--probe", action="append", default=[],
                        help="route to judge even if nothing links to it")
    args = parser.parse_args()

    seen, meta = crawl(args.base.rstrip("/"), probes=args.probe)
    report = render(seen, meta, args.label)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"routes": {p: vars(r) for p, r in seen.items()},
                       **meta}, fh, ensure_ascii=False, indent=2, default=list)
    print(f"{len(seen)} routes crawled, {len(meta['findings'])} findings "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
