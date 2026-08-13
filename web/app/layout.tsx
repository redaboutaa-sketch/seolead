import type { Metadata } from "next";

import "./globals.css";
import { Footer, Header, StagingBanner } from "@/components/Layout";
import { getSiteConfig } from "@/lib/api";

/**
 * `metadataBase` comes from the site's configured canonical origin, never from the
 * host serving the request. The staging host and the canonical host are different
 * things, and resolving canonicals against whatever answered the request is how a
 * page ends up telling a crawler it really lives on localhost.
 *
 * Still absent when no origin is configured — an incomplete canonical is honest;
 * a wrong one is not.
 */
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  const title = config?.brand_name ?? "Site en préproduction";
  const suffix = config?.seo.default_title_suffix ?? title;
  return {
    title: { default: title, template: `%s — ${suffix}` },
    description: config?.seo.default_meta_description ?? undefined,
    // Three independent conditions must hold before anything is indexable, and
    // the API computes them. Anything short of all three is noindex, nofollow.
    robots: config?.indexable
      ? { index: true, follow: true }
      : { index: false, follow: false, nocache: true },
    ...(config?.seo.canonical_origin
      ? { metadataBase: new URL(config.seo.canonical_origin) }
      : {}),
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  return (
    <html lang={locale}>
      <body>
        <a className="skip-link" href="#contenu">
          Aller au contenu
        </a>
        <StagingBanner config={config} />
        <Header config={config} locale={locale} />
        <main id="contenu">{children}</main>
        <Footer config={config} locale={locale} />
      </body>
    </html>
  );
}
