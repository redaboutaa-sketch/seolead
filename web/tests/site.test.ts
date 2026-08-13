import { describe, expect, it } from "vitest";

import { alternates, isKnownRoute, localizedPath } from "@/lib/site";
import type { SiteConfigDTO } from "@/lib/types";

const config = {
  site_id: "solar_be",
  vertical: "SOLAR_BE",
  brand_name: "Solar Belgium (nom provisoire)",
  brand_name_is_placeholder: true,
  domain: null,
  market: "BE",
  default_language: "fr",
  supported_languages: ["fr", "nl"],
  staging: true,
  indexable: false,
  locale_paths: { fr: "", nl: "/nl" },
  contact: {} as SiteConfigDTO["contact"],
  legal: {} as SiteConfigDTO["legal"],
  conversion: {} as SiteConfigDTO["conversion"],
  seo: {} as SiteConfigDTO["seo"],
  routes: [
    { path: "/", type: "HOME", locales: ["fr", "nl"] },
    { path: "/prix-panneaux-solaires", type: "LANDING_PAGE", locales: ["fr"] },
  ],
} as unknown as SiteConfigDTO;

describe("locale routing", () => {
  it("leaves the default locale unprefixed and prefixes the others", () => {
    expect(localizedPath(config, "fr", "/prix-panneaux-solaires")).toBe(
      "/prix-panneaux-solaires",
    );
    expect(localizedPath(config, "nl", "/prijs")).toBe("/nl/prijs");
    expect(localizedPath(config, "fr", "/")).toBe("/");
  });

  it("refuses to link to a path the site does not declare", () => {
    expect(isKnownRoute(config, "/prix-panneaux-solaires")).toBe(true);
    expect(isKnownRoute(config, "/rentabilite-panneaux-solaires")).toBe(false);
  });

  it("emits hreflang only for locales that actually have the page", () => {
    // A Dutch alternate for a page that exists only in French would point at a
    // 404, which is worse than having no alternate at all.
    expect(alternates(config, "/prix-panneaux-solaires", ["fr"])).toEqual([
      { locale: "fr", href: "/prix-panneaux-solaires" },
    ]);
    expect(alternates(config, "/", ["fr", "nl"]).map((a) => a.locale)).toEqual([
      "fr",
      "nl",
    ]);
  });
});
