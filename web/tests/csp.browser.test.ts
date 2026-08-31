/**
 * The Content-Security-Policy nonce contract (TRACER SL-T2).
 *
 * The bug these defend against was invisible to every check the project had.
 * `curl` returned HTTP 200 with complete, correct HTML. The pages painted. The
 * source-level assertions in `domain.test.ts` passed — the middleware really did
 * mint a per-request nonce and really did set it on the request header. What no
 * test looked at was whether the nonce in the *rendered HTML* was the same nonce
 * as the one in the *response header*, and on `/`, `/confidentialite`,
 * `/conditions` and the 404 it was not: those routes were statically prerendered,
 * so their HTML was frozen with whichever nonce (or none at all) existed when the
 * cache entry was written, while middleware minted a fresh one per request.
 *
 * Every script on those pages was therefore refused — 26 violations on the
 * homepage. It looked fine only because none of them shipped a Client Component;
 * a reproduction route carrying a single `useState` measured `hydrated: no`.
 *
 * So the assertions here are behavioural, not structural. The cheap ones use
 * `fetch` and compare header to body, which is the exact comparison that was
 * missing. The browser ones prove the consequence: framework JavaScript actually
 * executes, and a real Client Component actually hydrates.
 *
 * Requires a built app on TEST_BASE_URL. Skipped when the server or playwright is
 * unavailable, so it never blocks the unit suite.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";

/**
 * Every route the site serves as a document. The former static four are listed
 * first because they are the ones that were broken.
 */
const DOCUMENT_ROUTES = [
  "/",
  "/confidentialite",
  "/conditions",
  "/demande-etude",
  "/outils/estimation-solaire",
  "/prix-panneaux-solaires-belgique",
  "/cette-page-nexiste-pas",
];

const NONCE_IN_HEADER = /'nonce-([A-Za-z0-9+/=]+)'/;
const NONCE_ATTR = /nonce="([A-Za-z0-9+/=]+)"/g;

/** `<script>` tags carrying a nonce attribute. */
function bodyNonces(html: string): string[] {
  const found = new Set<string>();
  for (const match of html.matchAll(NONCE_ATTR)) {
    if (match[1]) found.add(match[1]);
  }
  return [...found];
}

/**
 * Script tags with no nonce.
 *
 * `application/ld+json` is exempt and only that: it is data, never executed, and
 * the CSP `script-src` directive does not gate it. Exempting it by exact type
 * rather than by "any script without a nonce" keeps the check sharp — an
 * executable inline script that lost its nonce still fails.
 */
function unNoncedExecutableScripts(html: string): string[] {
  const tags = html.match(/<script\b[^>]*>/g) ?? [];
  return tags.filter(
    (tag) => !tag.includes("nonce=") && !tag.includes("application/ld+json"),
  );
}

async function load(path: string) {
  const response = await fetch(`${BASE}${path}`, { redirect: "manual" });
  const html = await response.text();
  const csp = response.headers.get("content-security-policy") ?? "";
  return {
    status: response.status,
    html,
    csp,
    headerNonce: csp.match(NONCE_IN_HEADER)?.[1] ?? null,
    headers: response.headers,
  };
}

let reachable = false;
beforeAll(async () => {
  try {
    const probe = await fetch(BASE, { signal: AbortSignal.timeout(8000) });
    reachable = probe.ok;
  } catch {
    reachable = false;
  }
}, 30_000);

describe("CSP nonce — header and rendered HTML agree", () => {
  for (const path of DOCUMENT_ROUTES) {
    it(`serves ${path} with a nonce the response header actually allows`, async () => {
      if (!reachable) return;
      const page = await load(path);

      expect(page.headerNonce, `${path} has no nonce in its CSP header`).toBeTruthy();

      const inBody = bodyNonces(page.html);
      expect(inBody.length, `${path} rendered no nonced script at all`).toBeGreaterThan(0);

      // The whole bug, in one assertion: a frozen or absent body nonce fails here.
      expect(
        inBody,
        `${path}: HTML carries ${JSON.stringify(inBody)} but the header allows '${page.headerNonce}'`,
      ).toEqual([page.headerNonce]);

      expect(
        unNoncedExecutableScripts(page.html),
        `${path} has executable script tags with no nonce`,
      ).toEqual([]);
    }, 30_000);
  }

  it("mints a different nonce for every request", async () => {
    if (!reachable) return;
    // A nonce that repeats is not a nonce. This is also what fails if a route
    // slips back into the full route cache: the body nonce stops changing.
    const seen = new Set<string>();
    for (let i = 0; i < 4; i += 1) {
      const page = await load("/");
      seen.add(bodyNonces(page.html).join(","));
    }
    expect(seen.size, `homepage reused a nonce across requests: ${[...seen]}`).toBe(4);
  }, 60_000);
});

describe("CSP policy — strength is preserved", () => {
  it("keeps the strict directives and admits no unsafe escape hatch", async () => {
    if (!reachable) return;
    const { csp } = await load("/");

    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("'strict-dynamic'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");

    // The tempting "fix" for this bug was to allow inline scripts. It would have
    // re-opened the hole the policy exists to close, on the pages that render
    // owner-approved legal text.
    const scriptSrc = csp.split(";").find((part) => part.trim().startsWith("script-src")) ?? "";
    expect(scriptSrc, "script-src must not allow inline").not.toContain("'unsafe-inline'");
    expect(scriptSrc, "script-src must not allow eval").not.toContain("'unsafe-eval'");
    expect(scriptSrc, "script-src must not use a wildcard").not.toContain("*");
  }, 30_000);

  it("indexing signals agree: no blanket header, meta is the authority", async () => {
    if (!reachable) return;
    // Lancé le 2026-08-31 : les pages publiques ne portent PLUS d'en-tête
    // X-Robots-Tag — c'est lui qui a contredit la meta au lancement et fait
    // refuser chaque demande d'indexation. La meta (pilotée par la config,
    // fail-closed) est l'unique autorité ici.
    for (const path of ["/", "/confidentialite"]) {
      const page = await load(path);
      expect(page.headers.get("x-robots-tag")).toBeNull();
      expect(page.html).toContain('name="robots"');
    }
    // Les surfaces jamais indexables : en production, la basicauth Traefik
    // répond 401 à l'edge (rien n'est servi, rien n'est indexable) ; sans
    // Traefik, le middleware Next répond avec l'en-tête. Les deux formes
    // sont fermées ; un préview SERVI sans en-tête ne l'est pas.
    const preview = await fetch(`${BASE}/preview/fr/nimporte-quoi`);
    if (preview.status !== 401) {
      expect(preview.headers.get("x-robots-tag")).toBe(
        "noindex, nofollow, noarchive, nosnippet",
      );
    }
    // L'invariant est « /preview n'est jamais crawlable » : site lancé →
    // `Disallow: /preview/` explicite ; stack fail-closed (config
    // inaccessible) → `Disallow: /` qui le couvre aussi. Les deux formes
    // le respectent ; aucune autre n'est admise.
    const robots = await fetch(`${BASE}/robots.txt`).then((r) => r.text());
    expect(robots).toMatch(/^Disallow: \/(?:preview\/)?\s*$/m);
  }, 30_000);
});

describe("CSP in a real browser — the scripts actually run", () => {
  type Browser = Awaited<ReturnType<typeof launch>>;
  async function launch() {
    const { chromium } = await import("playwright");
    return chromium.launch();
  }
  let browser: Browser | null = null;
  let available = false;

  beforeAll(async () => {
    if (!reachable) return;
    try {
      browser = await launch();
      available = true;
    } catch {
      available = false;
    }
  }, 60_000);

  afterAll(async () => {
    await browser?.close();
  });

  async function visit(path: string) {
    if (!browser) throw new Error("no browser");
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const violations: string[] = [];
    page.on("console", (message) => {
      if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
    });
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 30_000 });
    await page.waitForTimeout(1500);
    return { context, page, violations };
  }

  for (const path of ["/", "/confidentialite", "/conditions"]) {
    it(`runs ${path} with no CSP violation and an executed RSC payload`, async () => {
      if (!available) return;
      const { context, page, violations } = await visit(path);

      expect(violations, `${path}:\n${violations.join("\n")}`).toEqual([]);

      // `__next_f` is the App Router's RSC payload. If CSP blocked the inline
      // scripts it stays empty — which is exactly what a passing DOM assertion
      // would have missed.
      const payload = await page.evaluate(() =>
        Array.isArray((self as unknown as { __next_f?: unknown[] }).__next_f)
          ? (self as unknown as { __next_f: unknown[] }).__next_f.length
          : 0,
      );
      expect(payload, `${path} executed no RSC payload script`).toBeGreaterThan(0);

      await context.close();
    }, 90_000);
  }

  it("hydrates a real Client Component", async () => {
    if (!available) return;
    // `LeadForm` is the site's only Client Component. Advancing a step is state
    // that only exists after hydration, so it cannot pass on server markup alone.
    const { context, page, violations } = await visit("/demande-etude");
    await page.route("**/api/**", (route) => route.abort());

    await page.locator('.choice input[name="owner_status"]').first().check();
    await page.locator('.choice input[name="property_type"]').first().check();
    await page.locator("#field-postcode").fill("1000");
    await page.locator('.form-actions button:has-text("Continuer")').click();
    await page.waitForTimeout(400);

    await expect
      .poll(async () => (await page.locator(".form-progress__label").innerText()).trim())
      .toContain("Étape 2");
    expect(violations, `violations:\n${violations.join("\n")}`).toEqual([]);

    await context.close();
  }, 90_000);

  it("refuses an inline script injected into the served HTML", async () => {
    if (!available) return;
    /*
     * The actual threat model, tested the only way it can be.
     *
     * Two earlier attempts asserted this from `page.evaluate` — appending a
     * `createElement` script, then calling `eval`. Both "passed" the escape and
     * failed the test, and neither was measuring the page: Playwright evaluates
     * in an isolated world that is exempt from the document's CSP, so nothing
     * run that way is ever blocked.
     *
     * So the script has to arrive the way a real injection would: inside the
     * server's own HTML, parsed by the browser under the real response headers.
     * The route is intercepted, the genuine response is fetched, an un-nonced
     * inline script is spliced in, and the original headers — CSP included — are
     * replayed. A parser-inserted script with no nonce must not execute, and
     * `'strict-dynamic'` does not rescue it: that directive propagates trust to
     * scripts created *by* already-trusted code, never to markup.
     */
    if (!browser) return;
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const violations: string[] = [];
    page.on("console", (message) => {
      if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
    });

    await page.route(`${BASE}/`, async (route) => {
      const original = await route.fetch();
      const body = (await original.text()).replace(
        "</body>",
        '<script id="injected">window.__csp_escape__ = true;</script></body>',
      );
      await route.fulfill({ response: original, body });
    });

    await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 30_000 });
    await page.waitForTimeout(1200);

    const present = await page.locator("#injected").count();
    expect(present, "the injected script never reached the document").toBe(1);

    const escaped = await page.evaluate(
      () => (window as unknown as { __csp_escape__?: boolean }).__csp_escape__ === true,
    );
    expect(escaped, "an un-nonced inline script executed — CSP is not enforcing").toBe(false);
    expect(
      violations.length,
      "the injected script raised no CSP violation, so nothing refused it",
    ).toBeGreaterThan(0);

    await context.close();
  }, 90_000);
});
