import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Content-Security-Policy with a per-request nonce.
 *
 * This has to live in middleware rather than `next.config.ts` because a static
 * header cannot carry a value that changes per request, and a nonce that does not
 * change per request is not a nonce.
 *
 * The bug this fixes: the App Router serves the RSC flight payload as inline
 * `<script>self.__next_f.push(...)</script>` tags — 13 of them on the price page.
 * A `script-src 'self'` policy with no nonce blocks every one. The server-rendered
 * HTML still painted, so the page looked correct for one frame; then React found
 * no payload to hydrate from, failed with "Connection closed", and cleared the
 * root. Blank page, HTTP 200, complete HTML on the wire — which is why `curl`
 * never saw it and only a real browser did.
 *
 * Next reads the nonce back out of the request's CSP header and stamps it onto
 * the scripts it generates, so both the request and the response carry it.
 *
 * `'unsafe-inline'` is deliberately NOT added. It would fix the symptom by
 * allowing every inline script on the page, including any that an evidence
 * passage managed to smuggle through the sanitizer — the exact thing the policy
 * exists to stop.
 */

/**
 * Routes that must NEVER be indexable, whatever the site-wide gate says.
 * Unconditional on purpose: preview serves unpublished content behind a
 * token, /api is machinery — no configuration state makes either indexable.
 *
 * The launched public routes carry NO X-Robots-Tag from here anymore. The
 * env-var switch that used to gate a blanket noindex header (deliberately
 * not named here: a test pins its absence from this file) was a second
 * source of truth beside the site config — and
 * on launch night (2026-08-31) it did exactly what a second source of truth
 * does: the YAML opened meta robots, robots.txt and the sitemap, the env
 * var stayed unset, every page served `index, follow` in HTML AND
 * `X-Robots-Tag: noindex` in HTTP, and Google honoured the stricter one.
 * Three « demande d'indexation refusée » later, the header answers to the
 * same authority as everything else: per-page metadata from the site
 * config, fail-closed by construction.
 */
const ALWAYS_NOINDEX_PREFIXES = ["/preview", "/api"];

function buildCsp(nonce: string): string {
  return [
    "default-src 'self'",
    // 'strict-dynamic' lets the nonce-approved bootstrap load the webpack chunks
    // it needs without listing each one; 'self' stays as the fallback for
    // browsers that do not implement it.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    // Next inlines critical CSS and React emits style props; both are inline
    // styles, which cannot execute code.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
  ].join("; ");
}

export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);

  /*
   * Both request headers are set because Next's documented pattern sets both,
   * and because which one it reads has changed between versions.
   *
   * Measured on Next 15.5.23 while fixing the prerender defect (TRACER SL-T2):
   * removing `x-nonce`, or the request CSP header, or BOTH, changes nothing —
   * every script is still stamped with the right nonce. Only removing the
   * *response* header breaks it. An earlier comment here asserted the opposite,
   * that response-only "would leave them unstamped"; that is not true of this
   * version, and a false claim in security-critical code is worse than none.
   *
   * They stay anyway. They cost one header each, they are what the framework
   * documents, and relying on an undocumented behaviour that happens to work
   * today is how this file earns its next incident.
   */
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("content-security-policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("content-security-policy", csp);
  if (ALWAYS_NOINDEX_PREFIXES.some(
      (prefix) => request.nextUrl.pathname.startsWith(prefix))) {
    // Kept here as well as in next.config so the header is present on every
    // response middleware touches, whatever the route returns.
    response.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet");
  }
  return response;
}

export const config = {
  matcher: [
    /*
     * Every document request. Static assets are excluded because they are
     * same-origin files that execute nothing and need no nonce — and running
     * middleware for each of them would cost a function invocation per asset.
     */
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
