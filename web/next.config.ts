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

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
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
