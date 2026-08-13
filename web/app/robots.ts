import type { MetadataRoute } from "next";

import { getSiteConfig } from "@/lib/api";

/**
 * The publication gate, expressed as robots.txt.
 *
 * `disallow: "/"` is the default and stays until the site has a domain, is out of
 * staging, and the owner has enabled indexing. Getting this wrong is not a bug you
 * fix later — an unfinished site in the index is a reputation cost that outlives
 * the fix.
 */
export const dynamic = "force-dynamic";

export default async function robots(): Promise<MetadataRoute.Robots> {
  const config = await getSiteConfig();
  if (!config?.indexable) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/preview/", "/api/"] }],
    sitemap: config.domain ? `https://${config.domain}/sitemap.xml` : undefined,
  };
}
