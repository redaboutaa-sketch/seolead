import type { Metadata } from "next";

import type { SiteConfigDTO } from "@/lib/types";

/**
 * One builder for every page's metadata, so OpenGraph, canonical and robots
 * cannot drift apart route by route.
 *
 * Two rules it enforces by construction:
 * - absolute URLs come from the configured canonical origin, never from the
 *   host serving the request — the staging host and the canonical host are
 *   different things;
 * - `og:image` is emitted ONLY when a real asset path is supplied. There is no
 *   brand visual today, so no page claims one; an OpenGraph card pointing at a
 *   404 is worse than a text card.
 */
export function pageMetadata({
  config,
  title,
  description,
  path,
  type = "website",
  locale,
  noindex = false,
  publishedTime,
  modifiedTime,
  imagePath,
}: {
  config: SiteConfigDTO | null;
  title: string;
  description?: string | null;
  path: string;
  type?: "website" | "article";
  locale?: string;
  noindex?: boolean;
  publishedTime?: string | null;
  modifiedTime?: string | null;
  imagePath?: string | null;
}): Metadata {
  const origin = config?.seo.canonical_origin ?? null;
  const url = origin ? `${origin}${path === "/" ? "" : path}` || origin : undefined;
  const indexable = Boolean(config?.indexable) && !noindex;

  return {
    title,
    description: description ?? undefined,
    alternates: url ? { canonical: url } : { canonical: path },
    robots: indexable
      ? { index: true, follow: true }
      : { index: false, follow: false, nocache: true },
    openGraph: {
      title,
      description: description ?? undefined,
      type,
      locale: locale ?? config?.default_language ?? "fr",
      siteName: config?.brand_name ?? undefined,
      ...(url ? { url } : {}),
      ...(imagePath && origin ? { images: [{ url: `${origin}${imagePath}` }] } : {}),
      ...(type === "article" && publishedTime ? { publishedTime } : {}),
      ...(type === "article" && modifiedTime ? { modifiedTime } : {}),
    },
    twitter: { card: "summary" },
  };
}
