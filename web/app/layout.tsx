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
    // A vector favicon: same sun-over-roof mark as the header wordmark, a few
    // hundred bytes, and it adapts to any tab size. `public/favicon.svg` is
    // same-origin, which the CSP's `img-src 'self'` requires.
    icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }] },
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
        {/*
          The brand green, so the mobile browser chrome matches the page instead
          of framing it in default grey. Declared here rather than as a token
          because a meta tag cannot read a CSS custom property.
        */}
        <meta name="theme-color" content="#0f6b4f" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0c1210" media="(prefers-color-scheme: dark)" />
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
