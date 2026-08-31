import type { MetadataRoute } from "next";

import { getSiteConfig, listPublished } from "@/lib/api";
import { contentPath, localizedPath } from "@/lib/site";

/**
 * PUBLISHED content only, and nothing at all while the site is not indexable.
 *
 * A sitemap is a publication act: it tells a crawler "these URLs are ready".
 * Listing staged pages would undo the robots rule above by another route.
 */
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const config = await getSiteConfig();
  if (!config?.indexable || !config.seo.sitemap_enabled) return [];

  const base = (config.seo.canonical_origin ?? "").replace(/\/$/, "");
  const entries: MetadataRoute.Sitemap = [
    { url: `${base}${localizedPath(config, config.default_language, "/")}`,
      changeFrequency: "monthly", priority: 1 },
  ];

  // Static public routes, from the declared route table — the same source the
  // renderer trusts for links, so the sitemap cannot list a page the site
  // would not link to. Legal pages are listed too: crawlable, low priority.
  //
  // The financing landing has its own second gate: it is or leads to
  // consumer-credit advertising, so it is listed ONLY once the offer registry
  // is publishable (owner validation AND legal review). A sitemap entry is a
  // publication act, and that page's publication belongs to the lawyer's
  // sign-off, not to the site-wide switch.
  const FINANCING_PATH = "/panneaux-solaires-sans-apport";
  const priorities: Record<string, number> = {
    CONVERSION: 0.9, LANDING_PAGE: 0.9, TOOL: 0.6, LEGAL: 0.3,
  };
  for (const route of config.routes) {
    if (route.path === "/") continue;
    if (route.path === FINANCING_PATH && !config.offer?.publishable) continue;
    for (const locale of route.locales) {
      if (!config.supported_languages.includes(locale)) continue;
      entries.push({
        url: `${base}${localizedPath(config, locale, route.path)}`,
        changeFrequency: "monthly",
        priority: priorities[route.type] ?? 0.5,
      });
    }
  }

  for (const locale of config.supported_languages) {
    for (const item of await listPublished(locale)) {
      entries.push({
        url: `${base}${contentPath(config, item)}`,
        lastModified: item.updated_at ? new Date(item.updated_at) : undefined,
        changeFrequency: "monthly",
        priority: 0.8,
      });
    }
  }

  // One entry per URL. A published page can also be a declared route (the
  // price landing is both); the content entry wins because it carries
  // lastModified, and it is pushed last.
  const byUrl = new Map(entries.map((entry) => [entry.url, entry]));
  return [...byUrl.values()];
}
