import type { NextConfig } from "next";

/**
 * Standalone output so the container ships a self-contained server instead of
 * `node_modules` — this VPS runs eleven other containers and the memory matters.
 *
 * `poweredByHeader` off and a strict CSP are here rather than in middleware
 * because they must apply to every response, including 404s and static assets,
 * and middleware does not run for all of them.
 */
const csp = [
  "default-src 'self'",
  // No inline or remote scripts. The site ships no third-party tag, and a CSP
  // that permits 'unsafe-inline' would not be worth writing down.
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "object-src 'none'",
].join("; ");

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
          { key: "Content-Security-Policy", value: csp },
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
