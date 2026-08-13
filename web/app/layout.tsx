import type { Metadata } from "next";

import "./globals.css";
import { Footer, Header, StagingBanner } from "@/components/Layout";
import { getSiteConfig } from "@/lib/api";

/**
 * `metadataBase` is intentionally absent while the site has no domain: Next would
 * otherwise resolve canonicals against localhost and emit URLs that are wrong the
 * moment the domain arrives.
 */
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  const title = config?.brand_name ?? "Site en préproduction";
  return {
    title: { default: title, template: `%s — ${title}` },
    description: config?.seo.default_meta_description ?? undefined,
    // Three independent conditions must hold before anything is indexable, and
    // the API computes them. Anything short of all three is noindex, nofollow.
    robots: config?.indexable
      ? { index: true, follow: true }
      : { index: false, follow: false, nocache: true },
    ...(config?.domain ? { metadataBase: new URL(`https://${config.domain}`) } : {}),
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
