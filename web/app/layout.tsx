import type { Metadata } from "next";
import { connection } from "next/server";

import "./globals.css";
import { Footer, Header, StagingBanner } from "@/components/Layout";
import { getSiteConfig, listPublished } from "@/lib/api";

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

/**
 * Every route is rendered at request time. This is a security requirement, not a
 * preference.
 *
 * `middleware.ts` mints a Content-Security-Policy nonce per request, and Next
 * stamps that nonce onto the scripts it generates by reading the CSP header off
 * the *request*. A statically prerendered page is built when no request exists,
 * so there is no nonce to stamp — and the response header still carries a fresh
 * one. Every script on such a page is then refused.
 *
 * That was not theoretical. Before this call, production served `/`,
 * `/confidentialite`, `/conditions` and the 404 from the full route cache, and a
 * browser reported 26, 16, 16 and 15 CSP violations on them respectively. The
 * pages still painted only because they ship no Client Component: nothing
 * hydrated, so nothing could blank. A single interactive component would have
 * reproduced the blank-page bug the CSP nonce exists to have fixed — a
 * reproduction route carrying one `useState` component measured `hydrated: no`.
 *
 * Next's own documentation is unambiguous: "To use a nonce, your page must be
 * dynamically rendered ... Static pages are generated at build time, when no
 * request or response headers exist—so no nonce can be injected."
 *
 * `connection()` is the documented opt-in, and it lives HERE rather than in each
 * page for one reason: a per-page opt-in is a rule someone has to remember. A new
 * route added next month would be static by default, would carry no nonce, and
 * would fail silently — a broken page with HTTP 200 and complete HTML, which is
 * precisely the failure mode this codebase has already been bitten by once. At
 * the root it cannot be forgotten.
 *
 * `connection()` rather than `export const dynamic = "force-dynamic"`: the latter
 * also flips the default fetch cache to `no-store`, which would put the SEO Lead
 * Factory API on the path of every request. `connection()` only says "wait for a
 * request before rendering", so `lib/api.ts` keeps its `revalidate` data cache and
 * the API is still called at most once per revalidation window.
 */
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await connection();
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  // The header needs to know what is actually published before it links to it.
  // This is the same cached fetch the homepage already makes, so it costs a
  // cache lookup rather than a round trip.
  const published = await listPublished(locale);
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
        <Header config={config} locale={locale} published={published} />
        <main id="contenu">{children}</main>
        <Footer config={config} locale={locale} published={published} />
      </body>
    </html>
  );
}
