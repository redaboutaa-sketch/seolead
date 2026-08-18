/**
 * No route may be statically prerendered (TRACER SL-T2).
 *
 * This is a security invariant expressed as a build assertion, and it is the
 * mutation guard for `await connection()` in `app/layout.tsx`.
 *
 * The CSP nonce is minted per request by `middleware.ts` and stamped onto scripts
 * by Next during server-side rendering, from the CSP header on the *request*. A
 * prerendered page is built when no request exists, so it gets no nonce — and the
 * response header still carries a fresh one, so every script on it is refused.
 * Next's own documentation states the constraint plainly: "To use a nonce, your
 * page must be dynamically rendered."
 *
 * The behavioural consequence is covered by `csp.browser.test.ts`. This test
 * catches the cause one layer earlier and without a server: remove
 * `connection()`, or add a page that renders statically, and the build starts
 * emitting prerendered HTML again — which is what these two artefacts record.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const NEXT_DIR = join(process.cwd(), ".next");
const built = existsSync(join(NEXT_DIR, "prerender-manifest.json"));

function htmlFilesUnder(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...htmlFilesUnder(full));
    else if (entry.endsWith(".html")) out.push(full.slice(NEXT_DIR.length + 1));
  }
  return out;
}

describe("render mode", () => {
  it.skipIf(!built)("prerenders no route at build time", () => {
    const manifest = JSON.parse(
      readFileSync(join(NEXT_DIR, "prerender-manifest.json"), "utf8"),
    ) as { routes?: Record<string, unknown>; dynamicRoutes?: Record<string, unknown> };

    expect(
      Object.keys(manifest.routes ?? {}),
      "a route is prerendered, so its HTML cannot carry the request's CSP nonce",
    ).toEqual([]);
    expect(Object.keys(manifest.dynamicRoutes ?? {})).toEqual([]);
  });

  it.skipIf(!built)("emits no prerendered HTML for any app route", () => {
    expect(
      htmlFilesUnder(join(NEXT_DIR, "server", "app")),
      "prerendered HTML found; these files are served with a stale or absent nonce",
    ).toEqual([]);
  });
});
