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

  const base = config.domain ? `https://${config.domain}` : "";
  const entries: MetadataRoute.Sitemap = [
    { url: `${base}${localizedPath(config, config.default_language, "/")}`,
      changeFrequency: "monthly", priority: 1 },
  ];

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
  return entries;
}
