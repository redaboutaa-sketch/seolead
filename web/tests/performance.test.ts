/**
 * The properties that keep the site fast, and the one that keeps it honest
 * about where it links (TRACER SL-T4).
 *
 * Lighthouse is the instrument that found these, but it is not a dependency of
 * this project and should not become one — it pulls ~120 packages to answer
 * questions that four `fetch` calls can answer. What is asserted here is the set
 * of *inputs* Lighthouse graded, each one something this codebase controls:
 *
 *   - `no-store` absent from documents, which is what let the page back into
 *     Chrome's back/forward cache
 *   - `immutable` still on the hashed assets, which the first attempt at the
 *     above silently destroyed
 *   - a meta description, which was failing invisibly behind the deliberate
 *     noindex failure in the same Lighthouse category
 *   - every link the site renders actually resolves
 *   - a transfer ceiling for a cold visit
 */
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

import { describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";
const BROWSER_AE = "gzip, deflate, br, zstd";
/** Compression happens at Traefik, so a byte budget only means anything there. */
const THROUGH_EDGE = BASE.startsWith("https://");

function raw(
  path: string,
  acceptEncoding = BROWSER_AE,
): Promise<{ status: number; bytes: number; headers: Record<string, string>; body: string }> {
  return new Promise((resolve, reject) => {
    const url = new URL(path.startsWith("http") ? path : `${BASE}${path}`);
    const send = url.protocol === "https:" ? httpsRequest : httpRequest;
    const req = send(
      {
        hostname: url.hostname,
        port: url.port || undefined,
        path: `${url.pathname}${url.search}`,
        method: "GET",
        headers: { "accept-encoding": acceptEncoding },
      },
      (res) => {
        let bytes = 0;
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => {
          bytes += c.length;
          if (chunks.length < 400) chunks.push(c);
        });
        res.on("end", () => {
          const headers: Record<string, string> = {};
          for (const [k, v] of Object.entries(res.headers)) headers[k] = String(v);
          resolve({
            status: res.statusCode ?? 0,
            bytes,
            headers,
            // Only meaningful when the response is not compressed; the callers
            // that read it ask for `identity`.
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
        res.on("error", reject);
      },
    );
    req.on("error", reject);
    req.end();
  });
}

let reachable = true;
try {
  await fetch(BASE, { signal: AbortSignal.timeout(8000) });
} catch {
  reachable = false;
}

describe.skipIf(!reachable)("back/forward cache eligibility", () => {
  for (const path of ["/", "/confidentialite", "/demande-etude"]) {
    it(`serves ${path} without no-store`, async () => {
      const res = await raw(path);
      const cc = res.headers["cache-control"] ?? "";
      /*
       * `no-store` disqualifies a page from Chrome's back/forward cache outright.
       * Next sets it by default on every dynamically rendered response, and since
       * TRACER SL-T2 every route is dynamic — so pressing Back re-fetched and
       * re-rendered the whole page. Lighthouse reported it as
       * `MainResourceHasCacheControlNoStore`.
       */
      expect(cc, `${path} sent Cache-Control: ${cc}`).not.toContain("no-store");
      // `no-cache` must stay: store if you like, but revalidate before reuse.
      expect(cc).toContain("no-cache");
    }, 30_000);
  }

  it("leaves the content-hashed assets immutable", async () => {
    const home = await raw("/", "identity");
    const asset = home.body.match(/\/_next\/static\/[^"']+\.(?:css|js)/)?.[0];
    expect(asset, "no hashed asset found in the document").toBeTruthy();

    const res = await raw(asset as string);
    /*
     * The first attempt at the bfcache fix applied the new Cache-Control to
     * `/:path*` and downgraded these from a year of immutable caching to
     * revalidate-every-time. That is a far worse regression than the one being
     * fixed, and it is invisible unless something asserts it.
     */
    expect(res.headers["cache-control"]).toContain("immutable");
    expect(res.headers["cache-control"]).toContain("max-age=31536000");
  }, 30_000);
});

describe.skipIf(!reachable)("search-engine readiness, minus the deliberate refusal", () => {
  for (const path of ["/", "/confidentialite", "/conditions"]) {
    it(`gives ${path} a meta description`, async () => {
      const res = await raw(path, "identity");
      const match = res.body.match(/<meta name="description" content="([^"]*)"/);
      /*
       * This failed silently for months. The Lighthouse SEO category was already
       * red because of the intentional noindex, so a second, real failure in the
       * same category looked like the same one problem.
       */
      expect(match?.[1], `${path} has no meta description`).toBeTruthy();
      expect((match?.[1] ?? "").length).toBeGreaterThan(40);
    }, 30_000);
  }

  it("the public page carries no X-Robots-Tag — meta is the one authority", async () => {
    const res = await raw("/");
    expect(res.headers["x-robots-tag"]).toBeUndefined();
  }, 30_000);
});

describe.skipIf(!reachable)("every link the site renders resolves", () => {
  it("has no internal link that 404s", async () => {
    const home = await raw("/", "identity");
    const hrefs = [...home.body.matchAll(/href="(\/[^"#?]*)"/g)]
      .map((m) => m[1] as string)
      .filter((h) => !h.startsWith("/_next/"))
      .filter((h) => h !== "/favicon.svg");
    const unique = [...new Set(hrefs)];
    expect(unique.length).toBeGreaterThan(3);

    const broken: string[] = [];
    for (const href of unique) {
      const res = await raw(href);
      if (res.status >= 400) broken.push(`${href} -> ${res.status}`);
    }
    /*
     * The bug this defends: the route list declares which paths the site MAY
     * link to, and the header treated that as which paths exist. A landing-page
     * route is only real once the owner publishes content at it, so the primary
     * navigation shipped a link to `/prix-panneaux-solaires`, which returned 404
     * — and spent an RSC prefetch on it with every page load.
     */
    expect(broken, `broken internal links: ${broken.join(", ")}`).toEqual([]);
  }, 120_000);
});

describe.skipIf(!reachable || !THROUGH_EDGE)("transfer budget", () => {
  it("keeps a cold visit under budget", async () => {
    const home = await raw("/", "identity");
    const assets = [...new Set([...home.body.matchAll(/\/_next\/static\/[^"']+\.(?:css|js)/g)].map((m) => m[0]))];
    expect(assets.length).toBeGreaterThan(3);

    const doc = await raw("/");
    let total = doc.bytes;
    for (const a of assets) total += (await raw(a)).bytes;

    /*
     * Measured at ~116 kB with brotli at the edge. The ceiling is deliberately
     * loose — this is a guard against a step change, such as a web font, a
     * raster hero or a new client-side library, not a ratchet on ordinary
     * content edits.
     */
    expect(total, `cold visit transferred ${total} B`).toBeLessThan(180_000);
  }, 120_000);
});
