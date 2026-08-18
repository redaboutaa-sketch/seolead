/**
 * Compression belongs to the edge (TRACER SL-T3).
 *
 * Two compressors sat in the request path and the weaker one kept winning. Next's
 * built-in compressor speaks only gzip; Traefik speaks brotli and zstd and
 * prefers brotli. A browser offers all of them in a single header, Next saw
 * `gzip`, compressed, and Traefik could not improve on a response that already
 * carried a Content-Encoding — so every visitor got the worst algorithm
 * available.
 *
 * Measured on production before the change: the homepage document was 19 737 B
 * as gzip, where the same document was 10 624 B as brotli.
 *
 * The assertions split by where they can actually be observed. The source ones
 * run anywhere. The wire ones need Traefik in the path, so they run only against
 * an https base URL — against the loopback backend the correct answer is the
 * opposite (no compression at all), and that is asserted too rather than skipped.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";
const THROUGH_EDGE = BASE.startsWith("https://");

/** What a current Chrome actually sends. */
const BROWSER_AE = "gzip, deflate, br, zstd";

async function fetchWith(path: string, acceptEncoding: string) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Accept-Encoding": acceptEncoding },
    redirect: "manual",
  });
  const body = Buffer.from(await response.arrayBuffer());
  return {
    status: response.status,
    encoding: response.headers.get("content-encoding"),
    bytes: body.byteLength,
  };
}

describe("configuration", () => {
  it("leaves compression to the edge rather than doing it in the app", () => {
    const config = readFileSync(join(process.cwd(), "next.config.ts"), "utf8");
    // Next's compressor is gzip-only. Leaving it on means it answers first and
    // Traefik's brotli is never reached.
    expect(config).toMatch(/compress:\s*false/);
  });

  it("compresses on every router that returns a body", () => {
    const overlay = readFileSync(
      join(process.cwd(), "..", "infra", "traefik", "docker-compose.public.yml"),
      "utf8",
    );

    const chain = (router: string) => {
      const match = overlay.match(
        new RegExp(`routers\\.${router}\\.middlewares:\\s*>-\\s*\\n\\s*([^\\n]+)`),
      );
      return match?.[1]?.trim() ?? "";
    };

    // The app no longer compresses anything, so a router without this middleware
    // serves its HTML raw. The preview router is the one that was missing it.
    expect(chain("monprojetsolaire")).toContain("monprojetsolaire-compress");
    expect(chain("monprojetsolaire-preview")).toContain("monprojetsolaire-compress");

    // The www router only ever emits a 308 with no body; compressing nothing
    // would be ceremony, and its absence here is deliberate rather than missed.
    expect(overlay).toMatch(
      /routers\.monprojetsolaire-www\.middlewares:\s*monprojetsolaire-www-to-apex/,
    );
  });
});

describe.skipIf(THROUGH_EDGE)("the application itself", () => {
  it("does not compress, even when the client asks for gzip", async () => {
    let reachable = true;
    const probe = await fetch(BASE).catch(() => null);
    if (!probe) reachable = false;
    if (!reachable) return;

    const gzip = await fetchWith("/", "gzip");
    // If this starts returning gzip, `compress: false` has been lost and Traefik
    // is being pre-empted again.
    expect(gzip.encoding, "the app compressed a response it should have passed on").toBeNull();
  }, 30_000);
});

describe.skipIf(!THROUGH_EDGE)("the wire, through Traefik", () => {
  it("serves the document as brotli to a browser", async () => {
    const browser = await fetchWith("/", BROWSER_AE);
    expect(browser.status).toBe(200);
    // The regression this defends: `gzip` here means the app started compressing
    // again and the edge never got to choose.
    expect(
      browser.encoding,
      `document served as ${browser.encoding} rather than brotli`,
    ).toBe("br");
  }, 30_000);

  it("keeps the document materially smaller than the gzip it replaced", async () => {
    const browser = await fetchWith("/", BROWSER_AE);
    const identity = await fetchWith("/", "identity");

    // Brotli measured at 10.6 kB against 19.7 kB of gzip. The bound is loose
    // enough to survive content edits and tight enough that a silent fallback to
    // gzip — or to no compression — fails it.
    expect(browser.bytes, `document was ${browser.bytes} B on the wire`).toBeLessThan(14_000);
    expect(browser.bytes).toBeLessThan(identity.bytes / 3);
  }, 30_000);

  it("compresses every document route, not only the homepage", async () => {
    for (const path of ["/", "/confidentialite", "/conditions", "/demande-etude"]) {
      const response = await fetchWith(path, BROWSER_AE);
      expect(
        response.encoding,
        `${path} was served uncompressed (${response.bytes} B)`,
      ).toBeTruthy();
    }
  }, 60_000);

  it("still refuses to index anything", async () => {
    // Compression negotiation touches headers; this is the one header set that
    // must never move, whatever else does.
    const response = await fetch(`${BASE}/`, { headers: { "Accept-Encoding": BROWSER_AE } });
    expect(response.headers.get("x-robots-tag")).toBe(
      "noindex, nofollow, noarchive, nosnippet",
    );
  }, 30_000);
});
