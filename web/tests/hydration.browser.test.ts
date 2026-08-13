/**
 * Regression: the published page must still be visible after hydration.
 *
 * This test exists because the bug it reproduces was invisible to every check we
 * had. `curl` returned complete, correct HTML with HTTP 200 — the server-rendered
 * markup was never the problem. A CSP without a nonce blocked the App Router's
 * inline RSC payload scripts, React hydrated against nothing, threw "Connection
 * closed", and cleared the root. The page was correct for one frame and blank
 * from the second frame onward.
 *
 * No assertion on an HTML string can catch that. Only executing the page can. So
 * this test drives a real browser engine against a real production build and
 * asserts what a visitor would actually see three seconds later.
 *
 * Requires a built app on TEST_BASE_URL (default: the local production server).
 * Skipped when playwright or the server is unavailable, so it never blocks the
 * unit suite — but it is part of the deployment procedure.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";
const PATH = process.env.TEST_PAGE_PATH ?? "/prix-panneaux-solaires-belgique";

type Browser = Awaited<ReturnType<typeof launch>>;
async function launch() {
  const { chromium } = await import("playwright");
  return chromium.launch();
}

let browser: Browser | null = null;
let available = false;

beforeAll(async () => {
  try {
    const probe = await fetch(`${BASE}${PATH}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!probe.ok) return;
    browser = await launch();
    available = true;
  } catch {
    available = false;
  }
}, 120_000);

afterAll(async () => {
  await browser?.close();
});

describe("published page survives hydration", () => {
  it("stays visible three seconds after load, with no page errors", async () => {
    if (!available || !browser) {
      console.warn(`skipped: ${BASE}${PATH} not reachable or playwright missing`);
      return;
    }

    const pageErrors: string[] = [];
    const cspViolations: string[] = [];
    const failedAssets: string[] = [];

    const page = await browser.newPage();
    page.on("pageerror", (e) => pageErrors.push(`${e.name}: ${e.message}`));
    page.on("console", (m) => {
      const text = m.text();
      if (m.type() === "error" && /Content Security Policy/i.test(text)) {
        cspViolations.push(text.slice(0, 120));
      }
    });
    page.on("response", (r) => {
      const url = r.url();
      if (/\/_next\/static\/.*\.(js|css)$/.test(url) && r.status() >= 400) {
        failedAssets.push(`${r.status()} ${url}`);
      }
    });

    await page.goto(`${BASE}${PATH}`, { waitUntil: "load", timeout: 30_000 });

    // The bug appeared within a frame of hydration; three seconds is well past it.
    await page.waitForTimeout(3000);

    const state = await page.evaluate(() => {
      const h1 = document.querySelector("h1");
      const text = document.body?.innerText ?? "";
      const visible = (el: Element | null) =>
        !!el && (el as HTMLElement).getClientRects().length > 0;
      return {
        h1Visible: visible(h1),
        h1Text: h1?.textContent ?? "",
        mainPresent: !!document.querySelector("main"),
        textLength: text.length,
        hasPrice: text.includes("4.000") && text.includes("14.000"),
        hasCta: text.includes("Obtenir mon estimation"),
      };
    });
    await page.close();

    // No inline script may be blocked: that is the failure mode, exactly.
    expect(cspViolations, `CSP blocked scripts:\n${cspViolations.join("\n")}`)
      .toEqual([]);
    expect(pageErrors, `uncaught errors:\n${pageErrors.join("\n")}`).toEqual([]);
    expect(failedAssets, `failed chunks:\n${failedAssets.join("\n")}`).toEqual([]);

    // What a visitor sees, three seconds in.
    expect(state.mainPresent).toBe(true);
    expect(state.h1Visible).toBe(true);
    expect(state.h1Text).toContain("Prix des Panneaux Solaires");
    expect(state.hasPrice).toBe(true);
    expect(state.hasCta).toBe(true);
    // The blank page reported ~0 characters of rendered text.
    expect(state.textLength).toBeGreaterThan(500);
  }, 120_000);
});
