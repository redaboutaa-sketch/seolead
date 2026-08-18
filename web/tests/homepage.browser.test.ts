/**
 * Regression protections for the premium redesign (US-SL-01 / TRACER SL-T1).
 *
 * These run in a real browser against a real production build, for the same
 * reason `hydration.browser.test.ts` does: the properties they defend —
 * horizontal overflow, computed tap-target size, whether an element is actually
 * rendered — are layout facts, and no assertion on an HTML string can see them.
 *
 * They are deliberately NOT pixel comparisons. A decorative shift must not fail
 * a build; a missing call to action must. Each test below corresponds to a
 * mutation that should break it:
 *
 *   remove the primary CTA          → "the primary call to action" fails
 *   remove the privacy link         → "the privacy notice stays reachable" fails
 *   break the mobile layout         → "no horizontal overflow" fails
 *   shrink a tap target             → "tap targets" fails
 *   let the homepage and the form disagree about the qualification steps
 *                                   → "the steps shown match the form" fails
 *
 * Consent semantics are not asserted here. They are enforced server-side and
 * already covered by `tests/test_lead_capture.py`, which is the layer that
 * actually decides whether a lead is accepted — asserting a checkbox in the
 * browser would test the weaker of the two.
 *
 * Requires a built app on TEST_BASE_URL. Skipped when playwright or the server
 * is unavailable, so it never blocks the unit suite.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://127.0.0.1:3100";
const FORM_PATH = "/demande-etude";

type Browser = Awaited<ReturnType<typeof launch>>;
async function launch() {
  const { chromium } = await import("playwright");
  return chromium.launch();
}

let browser: Browser | null = null;
let available = false;

beforeAll(async () => {
  try {
    const probe = await fetch(BASE, { signal: AbortSignal.timeout(8000) });
    if (!probe.ok) return;
    browser = await launch();
    available = true;
  } catch {
    available = false;
  }
}, 60_000);

afterAll(async () => {
  await browser?.close();
});

async function open(path: string, width: number, height = 900) {
  if (!browser) throw new Error("no browser");
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 30_000 });
  return { context, page };
}

const WIDTHS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 1024, height: 900 },
  { name: "desktop", width: 1440, height: 900 },
];

describe("homepage — conversion structure", () => {
  it("exposes exactly one h1", async () => {
    if (!available) return;
    const { context, page } = await open("/", 1440);
    expect(await page.locator("h1").count()).toBe(1);
    await context.close();
  }, 60_000);

  it("keeps the primary call to action, pointing at the conversion route", async () => {
    if (!available) return;
    const { context, page } = await open("/", 1440);
    const cta = page.locator('a[data-cta="primary"]');
    expect(await cta.count()).toBeGreaterThan(0);

    const first = cta.first();
    // `toBeVisible` is a playwright-test matcher; this suite runs under vitest,
    // so the visibility check is the locator's own boolean.
    expect(await first.isVisible()).toBe(true);
    expect(await first.getAttribute("href")).toBe(FORM_PATH);

    // A CTA whose label came from an empty config value is a broken CTA, and it
    // would otherwise render as a clickable void.
    const label = ((await first.textContent()) ?? "").trim();
    expect(label.length).toBeGreaterThan(4);
    await context.close();
  }, 60_000);

  it("keeps the privacy notice reachable from the footer", async () => {
    if (!available) return;
    const { context, page } = await open("/", 1440);
    const link = page.locator('footer a[href="/confidentialite"]');
    expect(await link.count()).toBeGreaterThan(0);
    expect(await link.first().isVisible()).toBe(true);
    await context.close();
  }, 60_000);

  it("shows the steps the form actually asks, in the same order", async () => {
    if (!available) return;
    // The homepage renders `conversion.form_steps` from the site config. If it
    // ever hard-codes them instead, this is the test that notices — the two
    // pages read the same source, so they cannot legitimately disagree.
    const home = await open("/", 1440);
    const shown = (
      await home.page.locator(".qualif__steps li").allTextContents()
    ).map((text) => text.replace(/^\s*\d+\s*/, "").trim());
    await home.context.close();

    expect(shown.length).toBeGreaterThan(0);

    const form = await open(FORM_PATH, 1440);
    const declared = (
      await form.page.locator(".form-aside li strong").allTextContents()
    ).map((text) => text.trim());
    await form.context.close();

    expect(shown).toEqual(declared);
  }, 90_000);
});

describe("layout — every supported width", () => {
  for (const size of WIDTHS) {
    it(`has no horizontal overflow at ${size.width}px (${size.name})`, async () => {
      if (!available) return;
      for (const path of ["/", FORM_PATH, "/confidentialite"]) {
        const { context, page } = await open(path, size.width, size.height);
        const overflow = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
        }));
        // One pixel of slack: sub-pixel rounding is not a layout defect.
        expect(
          overflow.scroll,
          `${path} overflows at ${size.width}px`,
        ).toBeLessThanOrEqual(overflow.client + 1);
        await context.close();
      }
    }, 120_000);
  }

  it("keeps tap targets comfortable on mobile", async () => {
    if (!available) return;
    const { context, page } = await open("/", 390, 844);
    const boxes = await page.locator("a.button, button.button").evaluateAll(
      (nodes) =>
        nodes
          // A control the layout hides at this width — the header CTA is
          // `display: none` below 52rem — has no tap target to be too small.
          .filter((node) => node.getBoundingClientRect().height > 0)
          .map((node) => {
            const rect = node.getBoundingClientRect();
            return { height: rect.height, text: (node.textContent ?? "").trim().slice(0, 30) };
          }),
    );
    expect(boxes.length).toBeGreaterThan(0);
    for (const box of boxes) {
      // 44px is the accessibility floor the design system commits to; the
      // `--large` variant sits well above it.
      expect(box.height, `"${box.text}" is only ${box.height}px tall`).toBeGreaterThanOrEqual(44);
    }
    await context.close();
  }, 60_000);
});

describe("accessibility — the properties the redesign could have broken", () => {
  it("gives the hero illustration an accessible name", async () => {
    if (!available) return;
    const { context, page } = await open("/", 1440);
    const named = await page.locator('.hero__visual svg[role="img"]').evaluate((node) => {
      const labelledBy = node.getAttribute("aria-labelledby");
      if (!labelledBy) return node.getAttribute("aria-label") ?? "";
      return document.getElementById(labelledBy)?.textContent?.trim() ?? "";
    });
    expect(named.length).toBeGreaterThan(20);
    await context.close();
  }, 60_000);

  it("labels every visible field on the qualification form", async () => {
    if (!available) return;
    const { context, page } = await open(FORM_PATH, 1440);
    // The honeypot is excluded on purpose: it is hidden from humans and from
    // assistive technology by design, and only a bot ever fills it.
    const unlabelled = await page
      .locator(".lead-form input:not([type=hidden])")
      .evaluateAll((nodes) =>
        nodes
          .filter((node) => !node.closest(".honeypot"))
          .filter((node) => {
            const id = node.getAttribute("id");
            const hasLabel = id ? !!document.querySelector(`label[for="${id}"]`) : false;
            const wrapped = !!node.closest("label");
            const aria = !!node.getAttribute("aria-label");
            return !(hasLabel || wrapped || aria);
          })
          .map((node) => node.getAttribute("name") ?? node.getAttribute("id") ?? "?"),
      );
    expect(unlabelled).toEqual([]);
    await context.close();
  }, 60_000);

  it("does not skip a heading level on the homepage", async () => {
    if (!available) return;
    const { context, page } = await open("/", 1440);
    const levels = await page
      .locator("h1, h2, h3, h4")
      .evaluateAll((nodes) => nodes.map((node) => Number(node.tagName.slice(1))));
    expect(levels[0]).toBe(1);
    for (let i = 1; i < levels.length; i += 1) {
      const previous = levels[i - 1] ?? 1;
      const current = levels[i] ?? 1;
      expect(
        current - previous,
        `h${previous} is followed by h${current}`,
      ).toBeLessThanOrEqual(1);
    }
    await context.close();
  }, 60_000);
});

describe("qualification flow — the visitor reaches the contact step cleanly", () => {
  it("shows no validation error on arrival at the final step, and posts no lead", async () => {
    if (!available || !browser) return;
    const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await context.newPage();

    // Every API call is aborted, so driving the form writes nothing: no
    // analytics row, no lead, no exporter path. The assertion below proves the
    // lead endpoint was never even reached.
    const attempted: string[] = [];
    await page.route("**/api/**", (route) => {
      attempted.push(new URL(route.request().url()).pathname);
      return route.abort();
    });

    await page.goto(`${BASE}${FORM_PATH}`, { waitUntil: "networkidle", timeout: 30_000 });
    await page.waitForTimeout(800);

    // Walk to the last step, answering only what each step requires.
    for (let step = 0; step < 8; step += 1) {
      if (await page.locator('.form-actions button[type="submit"]').count()) break;
      const groups = await page
        .locator(".choice input[type=radio]")
        .evaluateAll((nodes) => [...new Set(nodes.map((node) => node.getAttribute("name")))]);
      for (const group of groups) {
        await page.locator(`.choice input[name="${group}"]`).first().check();
      }
      const postcode = page.locator("#field-postcode");
      if (await postcode.count()) await postcode.fill("1000");
      await page.locator('.form-actions button:has-text("Continuer")').click();
      await page.waitForTimeout(250);
    }

    /*
     * The regression this defends: React reused one DOM button for "Continuer"
     * and for submit, so the click that advanced to step 5 also fired the
     * submit default action. The visitor arrived at the contact step already
     * showing errors for fields they had not been offered.
     */
    expect(await page.locator(".lead-form .field__error").count()).toBe(0);

    // Both consents present, neither pre-checked, marketing marked optional.
    const consents = await page
      .locator('.consent input[type="checkbox"]')
      .evaluateAll((nodes) =>
        nodes.map((node) => {
          const input = node as HTMLInputElement;
          return { id: input.id, checked: input.checked };
        }),
      );
    expect(consents.map((c) => c.id).sort()).toEqual([
      "field-consent_marketing",
      "field-consent_processing",
    ]);
    expect(consents.every((c) => c.checked === false)).toBe(true);

    expect(attempted).not.toContain("/api/leads");
    await context.close();
  }, 120_000);
});
