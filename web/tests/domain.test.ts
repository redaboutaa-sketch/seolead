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

  it("the X-Robots-Tag header guards preview and api, and ONLY them", () => {
    // Reading the source is the point. The guarantee changed on launch night
    // (2026-08-31): the env-var switch was a second source of truth beside
    // the site config and split against it — HTML said index, HTTP said
    // noindex, Google refused every indexation request. The header is now
    // UNCONDITIONAL on the never-indexable surfaces and ABSENT everywhere
    // else; per-page metadata (config-driven, fail-closed) is the one
    // authority for public routes.
    const source = readFileSync(new URL("../next.config.ts", import.meta.url), "utf-8");
    expect(source).toContain("X-Robots-Tag");
    expect(source).toContain('"/preview/:path*"');
    expect(source).toContain('"/api/:path*"');
    expect(source).not.toContain("SEOLEAD_ALLOW_INDEXING");
    const middleware = readFileSync(
      new URL("../middleware.ts", import.meta.url), "utf-8");
    expect(middleware).toContain('["/preview", "/api"]');
    expect(middleware).not.toContain("SEOLEAD_ALLOW_INDEXING");
    // The third — and on the wire, the decisive — ex-source: Traefik stamped
    // the same noindex header on every edge response via a customResponseHeader
    // label the launch runbook said to remove and nobody did. The app image was
    // irrelevant as long as this line existed.
    const overlay = readFileSync(
      new URL("../../infra/traefik/docker-compose.public.yml", import.meta.url),
      "utf-8");
    expect(overlay).not.toContain("customResponseHeaders.X-Robots-Tag");
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

describe("le service porte UN seul nom sur les pages publiques", () => {
  /*
   * Le 2026-09-02, la page confidentialité servait encore « Solar Belgium »
   * après un renommage qui se croyait complet — deux fois, dans des phrases
   * que JSX coupe par un retour à la ligne :
   *
   *     Les données personnelles collectées par l'intermédiaire du site Solar
   *     Belgium sont traitées sous la responsabilité de :
   *
   * `grep "Solar Belgium"` ne trouve rien là-dedans : il lit ligne à ligne,
   * quand le rendu, lui, recolle. Deux reconstructions d'image et un
   * .dockerignore ont été soupçonnés avant que la source ne soit relue
   * correctement. D'où cette assertion, qui aplatit les espaces AVANT de
   * chercher — la seule forme qui voie ce que le visiteur voit.
   */
  const NOMS_ABANDONNES = ["Solar Belgium"];

  for (const fichier of ["../app/confidentialite/page.tsx",
                         "../app/conditions/page.tsx"]) {
    it(`${fichier} ne rend aucun nom abandonné`, () => {
      let source: string;
      try {
        source = readFileSync(new URL(fichier, import.meta.url), "utf-8");
      } catch {
        return; // la page n'existe pas dans cette configuration
      }
      // Les commentaires du fichier PEUVENT nommer l'ancien nom : ils
      // expliquent précisément pourquoi il a disparu. Seul le rendu compte.
      const rendu = source
        .split("\n")
        .filter((ligne) => !ligne.trim().startsWith("//") && !ligne.trim().startsWith("*"))
        .join(" ")
        .replace(/\s+/g, " ");
      for (const nom of NOMS_ABANDONNES) {
        expect(rendu, `${fichier} rend encore « ${nom} »`).not.toContain(nom);
      }
    });
  }
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
