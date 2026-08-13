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

const ALLOW_INDEXING = process.env.SEOLEAD_ALLOW_INDEXING === "true";

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

  // Next looks for the nonce on the REQUEST's CSP header to stamp its own
  // scripts. Setting it only on the response would leave them unstamped and
  // reproduce the original bug with extra steps.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("content-security-policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("content-security-policy", csp);
  if (!ALLOW_INDEXING) {
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
