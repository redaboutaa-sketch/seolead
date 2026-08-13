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
        ],
      },
    ];
  },
};

export default nextConfig;
