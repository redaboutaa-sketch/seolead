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

  // Content-backed landing routes serve a page only once their content is
  // PUBLISHED — the published loop below lists those URLs, with lastModified.
  // Listing them from the route table alone put a 404 in the day-J sitemap
  // (found by publication simulation B: /prix-panneaux-solaires-belgique was
  // listed while its article still awaited owner approval). Same rule the
  // footer applies to its links. The financing landing is a page module, not
  // content — it keeps its own offer-registry gate.
  const published: { locale: string; url: string; updated_at: string | null }[] = [];
  for (const locale of config.supported_languages) {
    for (const item of await listPublished(locale)) {
      published.push({
        locale,
        url: `${base}${contentPath(config, item)}`,
        updated_at: item.updated_at ?? null,
      });
    }
  }
  const publishedUrls = new Set(published.map((item) => item.url));

  // /conditions declares itself noindex in its page module while its legal
  // text is the owner-pending placeholder — a sitemap must not list a page
  // that tells crawlers to ignore it. When the owner supplies the text and
  // the page's hardcoded noindex is lifted, remove the path here too (the
  // route stays in the table so the footer keeps linking it).
  const SELF_NOINDEX_PATHS = new Set(["/conditions"]);

  for (const route of config.routes) {
    if (route.path === "/") continue;
    if (SELF_NOINDEX_PATHS.has(route.path)) continue;
    if (route.path === FINANCING_PATH && !config.offer?.publishable) continue;
    for (const locale of route.locales) {
      if (!config.supported_languages.includes(locale)) continue;
      const url = `${base}${localizedPath(config, locale, route.path)}`;
      if (route.type === "LANDING_PAGE" && route.path !== FINANCING_PATH
          && !publishedUrls.has(url)) {
        continue;
      }
      entries.push({
        url,
        changeFrequency: "monthly",
        priority: priorities[route.type] ?? 0.5,
      });
    }
  }

  for (const item of published) {
    entries.push({
      url: item.url,
      lastModified: item.updated_at ? new Date(item.updated_at) : undefined,
      changeFrequency: "monthly",
      priority: 0.8,
    });
  }

  // One entry per URL. A published page can also be a declared route (the
  // price landing is both); the content entry wins because it carries
  // lastModified, and it is pushed last.
  const byUrl = new Map(entries.map((entry) => [entry.url, entry]));
  return [...byUrl.values()];
}
