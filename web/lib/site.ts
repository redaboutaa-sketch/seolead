/**
 * Locale and route helpers. Shared by server and client, so nothing here reads
 * an environment variable or touches the API.
 */
import type { PublishedContentDTO, SiteConfigDTO } from "./types";

export const FALLBACK_LOCALE = "fr";

export function localePrefix(config: SiteConfigDTO | null, locale: string): string {
  const configured = config?.locale_paths?.[locale];
  if (configured !== undefined) return configured;
  return locale === (config?.default_language ?? FALLBACK_LOCALE) ? "" : `/${locale}`;
}

export function localizedPath(
  config: SiteConfigDTO | null,
  locale: string,
  path: string,
): string {
  const prefix = localePrefix(config, locale);
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const joined = `${prefix}${normalized}`.replace(/\/{2,}/g, "/");
  return joined === "" ? "/" : joined;
}

/**
 * Whether the site may link to a path at all.
 *
 * The rule exists because a broken internal link is worse than a missing one: it
 * costs the visitor a 404 and the site a crawl budget. Only paths the site config
 * declares are linkable.
 */
export function isKnownRoute(config: SiteConfigDTO | null, path: string): boolean {
  if (!config) return false;
  return config.routes.some((route) => route.path === path);
}

export function knownRoutesForLocale(
  config: SiteConfigDTO | null,
  locale: string,
): { path: string; type: string }[] {
  if (!config) return [];
  return config.routes
    .filter((route) => route.locales.includes(locale))
    .map((route) => ({ path: route.path, type: route.type }));
}

/**
 * hreflang alternates. Only locales the site actually supports are emitted, and
 * never a locale for which no page exists — a hreflang pointing at a 404 is a
 * technical SEO defect, not a nicety.
 */
export function alternates(
  config: SiteConfigDTO | null,
  path: string,
  availableLocales: string[],
): { locale: string; href: string }[] {
  if (!config) return [];
  return config.supported_languages
    .filter((locale) => availableLocales.includes(locale))
    .map((locale) => ({ locale, href: localizedPath(config, locale, path) }));
}

export function contentPath(
  config: SiteConfigDTO | null,
  content: PublishedContentDTO,
): string {
  return localizedPath(config, content.locale, `/${content.slug}`);
}

/** Site name for display. Placeholders are shown as-is, never invented around. */
export function brandName(config: SiteConfigDTO | null): string {
  return config?.brand_name ?? "Site (configuration manquante)";
}
