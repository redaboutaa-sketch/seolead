import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CtaBlock, TrustSection } from "@/components/Cta";
import { Breadcrumbs } from "@/components/Layout";
import { PriceEvidenceBlock } from "@/components/PriceEvidence";
import { Prose } from "@/components/Prose";
import { getPublished, getSiteConfig } from "@/lib/api";
import { localizedPath } from "@/lib/site";

export const revalidate = 300;

interface Params {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  const content = await getPublished(locale, slug);
  if (!content) return { robots: { index: false, follow: false } };

  const indexable = config?.indexable && !content.meta.noindex;
  return {
    title: content.meta.title,
    description: content.meta.description ?? undefined,
    alternates: content.meta.canonical_path
      ? { canonical: content.meta.canonical_path }
      : undefined,
    robots: indexable
      ? { index: true, follow: true }
      : { index: false, follow: false, nocache: true },
    openGraph: {
      title: content.meta.title,
      description: content.meta.description ?? undefined,
      type: "article",
      locale,
    },
  };
}

export default async function ContentPage({ params }: Params) {
  const { slug } = await params;
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  const content = await getPublished(locale, slug);
  if (!content) notFound();

  return (
    <ContentView config={config} locale={locale} content={content} />
  );
}

/** Shared by the public route and the preview route, so they cannot diverge. */
export function ContentView({
  config,
  locale,
  content,
}: {
  config: Awaited<ReturnType<typeof getSiteConfig>>;
  locale: string;
  content: NonNullable<Awaited<ReturnType<typeof getPublished>>>;
}) {
  const answers = content.price_evidence?.answers ?? [];
  const unresolved =
    content.price_evidence?.core_answer_status === "CORE_QUESTION_UNRESOLVED";

  const breadcrumbJsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Accueil",
        item: localizedPath(config, locale, "/") },
      { "@type": "ListItem", position: 2, name: content.title },
    ],
  };

  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Accueil", href: localizedPath(config, locale, "/") },
          { label: content.title },
        ]}
      />
      <article className="container page">
        <h1>{content.title}</h1>

        {unresolved ? (
          <div className="notice notice--placeholder">
            <p>
              Les sources consultées ne permettent pas d&apos;établir un montant
              défendable pour cette question. Nous préférons le dire plutôt
              qu&apos;avancer un chiffre que rien ne soutient.
            </p>
          </div>
        ) : null}

        <Prose sections={content.sections} />

        <PriceEvidenceBlock
          answers={answers}
          observedRange={content.price_evidence?.observed_range ?? null}
        />

        <CtaBlock config={config} locale={locale} />
        <TrustSection />
      </article>

      {/*
        Only BreadcrumbList. No Organization (no real company data supplied), no
        LocalBusiness (no address), no AggregateRating (no reviews). Structured
        data that asserts things nobody supplied is fabrication with a schema.
      */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />
    </>
  );
}
