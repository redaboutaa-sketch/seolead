import type {
  PublishedContentDTO,
  SiteConfigDTO,
} from "@/lib/types";

/**
 * JSON-LD builders. One rule above all others, inherited from the content
 * pipeline: structured data that asserts things nobody supplied is fabrication
 * with a schema.
 *
 * Every builder returns `null` when the data behind it is missing, and the
 * caller renders nothing. `Organization` requires a legal name and a BCE
 * number; `LocalBusiness` additionally a complete address and a contact
 * channel — the readiness flags are computed server-side on the config, so a
 * half-filled block can never become a half-true schema. There are no builders
 * for Review, AggregateRating or author, because no verifiable review and no
 * named author exist. They will be written when the data does.
 *
 * `@id`s are stable and origin-anchored (`…/#website`, `…/#organization`,
 * `<page>#faq`), so the nodes of different pages reference one another as one
 * graph instead of redeclaring themselves under new identities.
 */

type Node = Record<string, unknown>;

function origin(config: SiteConfigDTO | null): string | null {
  return config?.seo.canonical_origin ?? null;
}

export function websiteNode(config: SiteConfigDTO | null): Node | null {
  const base = origin(config);
  if (!base || !config) return null;
  return {
    "@type": "WebSite",
    "@id": `${base}/#website`,
    url: base,
    name: config.brand_name,
    inLanguage: config.default_language,
    ...(organizationNode(config)
      ? { publisher: { "@id": `${base}/#organization` } }
      : {}),
  };
}

export function organizationNode(config: SiteConfigDTO | null): Node | null {
  const base = origin(config);
  const org = config?.organization;
  if (!base || !org || !org.organization_schema_ready) return null;
  return {
    "@type": org.local_business_schema_ready ? "LocalBusiness" : "Organization",
    "@id": `${base}/#organization`,
    name: config.brand_name,
    legalName: org.legal_name,
    identifier: org.bce_number,
    url: base,
    ...(org.local_business_schema_ready
      ? {
          address: {
            "@type": "PostalAddress",
            streetAddress: org.address.street,
            postalCode: org.address.postal_code,
            addressLocality: org.address.city,
            addressCountry: org.address.country,
          },
          ...(org.phone ? { telephone: org.phone } : {}),
          ...(org.email ? { email: org.email } : {}),
        }
      : {}),
    ...(org.service_areas.length
      ? { areaServed: org.service_areas.map((a) => ({ "@type": "Place", name: a })) }
      : {}),
    ...(org.logo_path ? { logo: `${base}${org.logo_path}` } : {}),
    ...(org.same_as.length ? { sameAs: org.same_as } : {}),
  };
}

export interface FaqEntry {
  question: string;
  answer: string;
}

export function faqNode(
  config: SiteConfigDTO | null,
  pagePath: string,
  entries: FaqEntry[],
): Node | null {
  const base = origin(config);
  if (!base || entries.length === 0) return null;
  return {
    "@type": "FAQPage",
    "@id": `${base}${pagePath === "/" ? "" : pagePath}/#faq`.replace(/\/\/#/, "/#"),
    mainEntity: entries.map(({ question, answer }) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
}

export function webPageNode(
  config: SiteConfigDTO | null,
  pagePath: string,
  name: string,
  description?: string,
): Node | null {
  const base = origin(config);
  if (!base) return null;
  const url = `${base}${pagePath === "/" ? "" : pagePath}`;
  return {
    "@type": "WebPage",
    "@id": `${url}/#webpage`.replace(/\/\/#/, "/#"),
    url,
    name,
    ...(description ? { description } : {}),
    isPartOf: { "@id": `${base}/#website` },
    inLanguage: config?.default_language ?? "fr",
  };
}

/**
 * The study/estimation service — the one service that verifiably exists today.
 * Deliberately carries NO offers, no price and no rating: the offer facts live
 * in the first-party registry and appear here only once it is publishable.
 */
export function serviceNode(
  config: SiteConfigDTO | null,
  pagePath: string,
): Node | null {
  const base = origin(config);
  if (!base || !config) return null;
  return {
    "@type": "Service",
    "@id": `${base}/#service-etude`,
    name: "Étude et estimation de projet photovoltaïque résidentiel",
    serviceType: "Étude de projet photovoltaïque",
    provider: organizationNode(config)
      ? { "@id": `${base}/#organization` }
      : { "@type": "Organization", name: config.brand_name },
    areaServed: { "@type": "Country", name: "Belgique" },
    url: `${base}${pagePath}`,
  };
}

export function articleNode(
  config: SiteConfigDTO | null,
  content: PublishedContentDTO,
  pagePath: string,
): Node | null {
  const base = origin(config);
  if (!base) return null;
  const url = `${base}${pagePath}`;
  return {
    "@type": "Article",
    "@id": `${url}/#article`.replace(/\/\/#/, "/#"),
    headline: content.title,
    url,
    inLanguage: content.locale,
    isPartOf: { "@id": `${base}/#website` },
    ...(content.published_at ? { datePublished: content.published_at } : {}),
    ...(content.updated_at ? { dateModified: content.updated_at } : {}),
    ...(organizationNode(config)
      ? { publisher: { "@id": `${base}/#organization` } }
      : {}),
    // No `author`: none exists. An invented byline is the exact fabrication
    // this module refuses.
  };
}

/** Assemble non-null nodes into one @graph document, or null if none. */
export function graph(...nodes: (Node | null)[]): string | null {
  const kept = nodes.filter((n): n is Node => n !== null);
  if (kept.length === 0) return null;
  return JSON.stringify({ "@context": "https://schema.org", "@graph": kept });
}
