"""Generated markdown → sanitized structured sections.

Generated content is untrusted input. Not because the model is adversarial, but
because the model's output is derived from web pages that are, and a source page
that contains `<script>` or `javascript:` can reach the draft through a quoted
passage. Rendering a draft body as HTML would make the site's XSS surface equal to
the whole retrieved corpus.

So nothing renders as HTML. Markdown is parsed into a small closed set of typed
nodes — heading, paragraph, list, price_list — each carrying plain text and a
short allowlist of inline marks. Anything the parser does not recognise is dropped
rather than passed through, which is the only default that stays safe when the
input changes.

The frontend receives these nodes and maps them to components. It never calls
`dangerouslySetInnerHTML`, and there is no code path by which it could.
"""
from __future__ import annotations

import re

# Inline marks the site is willing to render. Everything else becomes plain text.
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_BARE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Anything that can execute, embed or navigate off-site is removed outright.
_DANGEROUS_BLOCK = re.compile(
    r"<\s*(script|iframe|object|embed|style|link|meta|form|svg|base)\b[^>]*>"
    r"(?:.*?<\s*/\s*\1\s*>)?",
    re.IGNORECASE | re.DOTALL)
_ANY_TAG = re.compile(r"<[^>]*>")
_DANGEROUS_SCHEME = re.compile(
    r"(?:javascript|data|vbscript|file)\s*:", re.IGNORECASE)
# HTML entities that decode to a tag delimiter — a second encoding layer.
_ENCODED_ANGLE = re.compile(r"&(?:#0*(?:60|62)|lt|gt);", re.IGNORECASE)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")

_MAX_TEXT = 4000
_MAX_ITEMS = 40
_MAX_SECTIONS = 60

# A list item that leads with a figure is a price answer, not prose. Detected so
# the site can render it through the evidence component rather than as a bullet.
_PRICE_ITEM = re.compile(
    r"\d[\d\s.,]*\s*(?:€|eur\b|euros?\b)|(?:€|eur)\s*\d", re.IGNORECASE)


def strip_unsafe(text: str) -> str:
    """Remove anything executable, embeddable or navigable from a text run."""
    cleaned = _DANGEROUS_BLOCK.sub(" ", text or "")
    cleaned = _ENCODED_ANGLE.sub(" ", cleaned)
    # Tags are removed, not escaped: the renderer emits text nodes, so an escaped
    # tag would only show the reader angle brackets.
    cleaned = _ANY_TAG.sub(" ", cleaned)
    cleaned = _DANGEROUS_SCHEME.sub(" ", cleaned)
    return cleaned


def _inline(text: str) -> list[dict]:
    """Split a line into text runs with an allowlisted mark.

    Links are flattened to their label. Phase 3.4 blocks outbound links at QA, and
    this is the structural counterpart: even if a link survived generation, the
    site has no node type that could render one.
    """
    text = strip_unsafe(text)
    text = _MD_LINK.sub(lambda m: m.group(1) or "", text)
    text = _BARE_URL.sub(" ", text)

    runs: list[dict] = []
    position = 0
    pattern = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
    for match in pattern.finditer(text):
        if match.start() > position:
            plain = text[position:match.start()]
            if plain.strip():
                runs.append({"text": plain, "mark": None})
        if match.group(1) is not None:
            runs.append({"text": match.group(1), "mark": "strong"})
        elif match.group(2) is not None:
            runs.append({"text": match.group(2), "mark": "code"})
        else:
            runs.append({"text": match.group(3), "mark": "em"})
        position = match.end()
    tail = text[position:]
    if tail.strip():
        runs.append({"text": tail, "mark": None})

    if not runs and text.strip():
        runs.append({"text": text, "mark": None})
    return [{"text": r["text"][:_MAX_TEXT], "mark": r["mark"]} for r in runs]


def _plain(text: str) -> str:
    stripped = strip_unsafe(text)
    stripped = _MD_LINK.sub(lambda m: m.group(1) or "", stripped)
    stripped = _BARE_URL.sub(" ", stripped)
    stripped = _BOLD.sub(r"\1", stripped)
    stripped = _ITALIC.sub(r"\1", stripped)
    stripped = _CODE.sub(r"\1", stripped)
    return " ".join(stripped.split())[:_MAX_TEXT]


def parse_sections(body: str) -> list[dict]:
    """Parse a generated markdown body into typed, sanitized sections.

    The output is a flat list. Nesting would be nicer to render and much harder to
    validate, and every page this system generates is one H1 followed by H2
    sections — a shape a flat list expresses exactly.
    """
    sections: list[dict] = []
    paragraph: list[str] = []
    items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            joined = " ".join(paragraph).strip()
            if joined:
                sections.append({"type": "paragraph", "runs": _inline(joined),
                                 "text": _plain(joined)})
            paragraph.clear()

    def flush_items() -> None:
        if not items:
            return
        priced = sum(1 for item in items if _PRICE_ITEM.search(item))
        kind = "price_list" if priced and priced >= len(items) / 2 else "list"
        sections.append({
            "type": kind,
            "items": [{"runs": _inline(i), "text": _plain(i)}
                      for i in items[:_MAX_ITEMS]],
        })
        items.clear()

    for raw_line in (body or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_items()
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_items()
            text = _plain(heading.group(2))
            if text:
                sections.append({"type": "heading",
                                 "level": min(len(heading.group(1)), 6),
                                 "text": text})
            continue

        bullet = _BULLET.match(line) or _ORDERED.match(line)
        if bullet:
            flush_paragraph()
            items.append(bullet.group(1))
            continue

        flush_items()
        paragraph.append(line.strip())

    flush_paragraph()
    flush_items()
    return sections[:_MAX_SECTIONS]


def contains_external_link(body: str) -> bool:
    """Whether the raw body carries a link. Used as a publication precondition."""
    return bool(_MD_LINK.search(body or "") or _BARE_URL.search(body or ""))


def section_text(sections: list[dict]) -> str:
    """Flatten sections back to plain text, for QA re-verification at publish."""
    parts: list[str] = []
    for section in sections or []:
        if section.get("type") == "heading":
            parts.append(str(section.get("text", "")))
        elif section.get("type") == "paragraph":
            parts.append(str(section.get("text", "")))
        else:
            parts.extend(str(i.get("text", "")) for i in section.get("items") or [])
    return "\n".join(p for p in parts if p)
