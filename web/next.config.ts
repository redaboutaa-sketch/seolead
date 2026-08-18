import type { NextConfig } from "next";

/**
 * Standalone output so the container ships a self-contained server instead of
 * `node_modules` — this VPS runs eleven other containers and the memory matters.
 *
 * `poweredByHeader` off and a strict CSP are here rather than in middleware
 * because they must apply to every response, including 404s and static assets,
 * and middleware does not run for all of them.
 */
/**
 * Content-Security-Policy is NOT set here.
 *
 * It needs a per-request nonce for the App Router's inline RSC payload scripts,
 * and a value in this file is baked in at build time. It lives in `middleware.ts`.
 * Setting it in both places would emit two CSP headers, and a browser enforces
 * the intersection — so the static, nonce-less one would silently win and
 * reinstate the blank-page bug.
 */

/**
 * Indexing is refused at the HTTP layer unless explicitly enabled at build time.
 *
 * Fail-closed on purpose. `SiteConfig.allow_indexing` already gates robots.txt and
 * the per-page meta tag, but those are rendered by the app; this header is emitted
 * for every response including static assets and error pages, and it is the one
 * that a misconfigured route cannot bypass.
 *
 * Turning it off requires BOTH this env var and the SiteConfig flag — two
 * independent switches, matching the three-condition design of `is_indexable`.
 */
const allowIndexing = process.env.SEOLEAD_ALLOW_INDEXING === "true";

/**
 * Compression is the edge's job, not the app's.
 *
 * Next's built-in compressor speaks only gzip. Traefik, which fronts every public
 * request, speaks brotli and zstd and prefers brotli. But a browser offers
 * `gzip, deflate, br, zstd` in one header, Next sees `gzip`, compresses, and
 * Traefik cannot improve on a response that already carries a Content-Encoding.
 * The weakest available algorithm therefore won every negotiation.
 *
 * Measured on production, homepage document:
 *
 *   browser Accept-Encoding  → gzip  19 737 B   ← what visitors actually got
 *   br offered without gzip  → br    10 624 B   ← what Traefik would have sent
 *
 * The gap is wide because this HTML is a streamed dynamic response and Next
 * compresses those at a fast, weak level; the same bytes at `gzip -9` are
 * 13 651 B. Handing the document to Traefik takes it to 10.6 kB — 46 % off the
 * one resource on the critical path, for a homeowner on 4G in a Walloon village.
 *
 * The cost of this line is that anything reaching the app WITHOUT passing through
 * Traefik is served uncompressed: the loopback port 3100, which exists for
 * operator diagnostics only. `infra/traefik/docker-compose.public.yml` therefore
 * carries the compress middleware on every router that returns a body — the
 * preview router included, which it was not before this change.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  compress: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          ...(allowIndexing
            ? []
            : [
                {
                  key: "X-Robots-Tag",
                  value: "noindex, nofollow, noarchive, nosnippet",
                },
              ]),
        ],
      },
    ];
  },
};

export default nextConfig;
