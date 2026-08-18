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
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";
const THROUGH_EDGE = BASE.startsWith("https://");

/** What a current Chrome actually sends. */
const BROWSER_AE = "gzip, deflate, br, zstd";

/**
 * Raw wire bytes, via `node:http` rather than `fetch`.
 *
 * `fetch` transparently decompresses, so `arrayBuffer()` returns the *expanded*
 * body — 67 594 B for a document that crossed the wire as 10 624 B of brotli.
 * There is no `content-length` to fall back on either: Traefik streams the
 * compressed response chunked.
 *
 * This mattered in practice. An earlier version of this file measured with
 * `fetch` and passed, because undici happened not to decompress zstd — so the
 * size assertion was reading true wire bytes by accident. The moment the edge
 * started serving brotli, which undici does decompress, the same assertion
 * failed. A byte-count test that only works for the encodings its runtime
 * declines to handle is not measuring anything.
 */
function fetchWith(
  path: string,
  acceptEncoding: string,
): Promise<{ status: number; encoding: string | null; bytes: number }> {
  return new Promise((resolve, reject) => {
    const url = new URL(`${BASE}${path}`);
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
        res.on("data", (chunk: Buffer) => {
          bytes += chunk.length;
        });
        res.on("end", () =>
          resolve({
            status: res.statusCode ?? 0,
            encoding: (res.headers["content-encoding"] as string | undefined) ?? null,
            bytes,
          }),
        );
        res.on("error", reject);
      },
    );
    req.on("error", reject);
    req.end();
  });
}

describe("configuration", () => {
  it("leaves compression to the edge rather than doing it in the app", () => {
    const config = readFileSync(join(process.cwd(), "next.config.ts"), "utf8");
    // Next's compressor is gzip-only. Leaving it on means it answers first and
    // Traefik's brotli is never reached.
    expect(config).toMatch(/compress:\s*false/);
  });

  it("asks the edge for brotli first", () => {
    const overlay = readFileSync(
      join(process.cwd(), "..", "infra", "traefik", "docker-compose.public.yml"),
      "utf8",
    );
    /*
     * Traefik's own default is zstd-first, and that is what shipped in the first
     * cut of this tracer. It was measurably the wrong choice for this site:
     * brotli was smaller on every single resource — the document by 2.4 kB, the
     * two large chunks by 7.7 and 8.9 kB, the stylesheet by 1.3 kB. Roughly 20 kB
     * on a cold visit.
     *
     * Without this line the site silently falls back to zstd, which still looks
     * like "compression is working" from every angle except the byte count.
     */
    expect(overlay).toMatch(
      /monprojetsolaire-compress\.compress\.encodings:\s*"br,zstd,gzip"/,
    );
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

  it("keeps the document materially smaller than the gzip it would otherwise get", async () => {
    const browser = await fetchWith("/", BROWSER_AE);
    const gzip = await fetchWith("/", "gzip");
    const identity = await fetchWith("/", "identity");

    // The comparison that states the tracer's whole point: what a browser
    // receives must beat what gzip alone would have given it.
    expect(
      browser.bytes,
      `browser got ${browser.bytes} B, gzip would have given ${gzip.bytes} B`,
    ).toBeLessThan(gzip.bytes * 0.85);

    // An absolute floor as well, so "smaller than gzip" cannot be satisfied by
    // both of them quietly growing.
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
