import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { localizedPath } from "@/lib/site";
import type { SiteConfigDTO } from "@/lib/types";

const DOMAIN = "monprojetsolaire.be";
const ORIGIN = `https://${DOMAIN}`;

const config = {
  site_id: "solar_be",
  brand_name: "Mon Projet Solaire",
  brand_name_is_placeholder: false,
  domain: DOMAIN,
  default_language: "fr",
  supported_languages: ["fr", "nl"],
  staging: true,
  indexable: false,
  locale_paths: { fr: "", nl: "/nl" },
  seo: {
    canonical_origin: ORIGIN,
    default_title_suffix: "Mon Projet Solaire",
    default_meta_description: null,
    organization_schema: false,
    sitemap_enabled: true,
    allow_indexing: false,
  },
  routes: [{ path: "/", type: "HOME", locales: ["fr", "nl"] }],
} as unknown as SiteConfigDTO;

describe("canonical origin", () => {
  it("never resolves against localhost or a container hostname", () => {
    const base = config.seo.canonical_origin!;
    for (const forbidden of ["localhost", "127.0.0.1", "seolead_web", ".internal"]) {
      expect(base).not.toContain(forbidden);
    }
    expect(base).toBe(ORIGIN);
    expect(base.startsWith("https://")).toBe(true);
  });

  it("builds locale paths that sit under the production origin", () => {
    expect(`${ORIGIN}${localizedPath(config, "fr", "/prix")}`).toBe(`${ORIGIN}/prix`);
    expect(`${ORIGIN}${localizedPath(config, "nl", "/prijzen")}`).toBe(
      `${ORIGIN}/nl/prijzen`,
    );
  });
});

describe("indexing gate", () => {
  it("a configured domain does not make the site indexable", () => {
    expect(config.domain).toBe(DOMAIN);
    expect(config.indexable).toBe(false);
    expect(config.seo.allow_indexing).toBe(false);
    expect(config.staging).toBe(true);
  });

  it("the X-Robots-Tag header is fail-closed in next.config", () => {
    // Reading the source is the point: the guarantee is that the DEFAULT is
    // noindex, and only an explicit env var removes the header.
    const source = readFileSync(new URL("../next.config.ts", import.meta.url), "utf-8");
    expect(source).toContain('process.env.SEOLEAD_ALLOW_INDEXING === "true"');
    expect(source).toContain("X-Robots-Tag");
    expect(source).toMatch(/allowIndexing\s*\?\s*\[\]/);
  });

  it("robots.ts disallows everything unless the site is indexable", () => {
    const source = readFileSync(new URL("../app/robots.ts", import.meta.url), "utf-8");
    expect(source).toContain("if (!config?.indexable)");
    expect(source).toContain('disallow: "/"');
  });

  it("sitemap.ts emits nothing unless the site is indexable", () => {
    const source = readFileSync(new URL("../app/sitemap.ts", import.meta.url), "utf-8");
    expect(source).toContain("if (!config?.indexable");
    expect(source).toContain("return []");
  });
});

describe("content-security-policy", () => {
  it("is emitted from middleware only, never from next.config", () => {
    // Two CSP headers means the browser enforces the intersection, so a static
    // nonce-less policy would silently win and blank the page again.
    const config = readFileSync(new URL("../next.config.ts", import.meta.url), "utf-8");
    expect(config).not.toMatch(/key:\s*"Content-Security-Policy"/);
    expect(config).not.toMatch(/"script-src/);
  });

  it("carries a per-request nonce for the App Router's inline RSC scripts", () => {
    const mw = readFileSync(new URL("../middleware.ts", import.meta.url), "utf-8");
    expect(mw).toContain("randomUUID");
    expect(mw).toMatch(/script-src 'self' 'nonce-\$\{nonce\}'/);
    // Next reads the nonce off the REQUEST header; response-only would not work.
    expect(mw).toMatch(/requestHeaders\.set\("content-security-policy"/);
  });

  it("does not fall back to unsafe-inline", () => {
    const mw = readFileSync(new URL("../middleware.ts", import.meta.url), "utf-8");
    const scriptSrc = mw.match(/script-src[^`\n]*/)?.[0] ?? "";
    expect(scriptSrc).not.toContain("unsafe-inline");
  });
});

describe("publication state still gates the public route", () => {
  it("the public content route reads published content only", () => {
    const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf-8");
    expect(api).toContain("/content/${locale}/");
    // Preview paths are separate functions and each requires the preview token.
    expect(api).toContain("SEOLEAD_PREVIEW_TOKEN");
    expect(api).toMatch(/getPreview[\s\S]*?if \(!token\) return null;/);
    expect(api).toMatch(/getDraftPreview[\s\S]*?if \(!token\) return null;/);
  });
});
