import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CtaBlock, TrustSection } from "@/components/Cta";
import { Breadcrumbs } from "@/components/Layout";
import { PriceEvidenceBlock } from "@/components/PriceEvidence";
import { Prose } from "@/components/Prose";
import { SourcesBlock } from "@/components/Sources";
import { getPublished, getSiteConfig } from "@/lib/api";
import { contentPath, localizedPath } from "@/lib/site";
import { articleNode, graph, websiteNode } from "@/lib/jsonld";
import { pageMetadata } from "@/lib/metadata";

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

  // Shared builder (P2.4): OG url/site_name, twitter card and article dates
  // come from one place. The per-content noindex still overrides.
  return pageMetadata({
    config,
    title: content.meta.title,
    description: content.meta.description,
    path: contentPath(config, content),
    type: "article",
    locale,
    noindex: content.meta.noindex,
    publishedTime: content.published_at,
    modifiedTime: content.updated_at,
  });
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
  const sources = content.sources ?? [];
  const unresolved =
    content.price_evidence?.core_answer_status === "CORE_QUESTION_UNRESOLVED";

  const breadcrumbNode = {
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Accueil",
        item: localizedPath(config, locale, "/") },
      { "@type": "ListItem", position: 2, name: content.title },
    ],
  };
  // Article with its real dates, WebSite for the graph anchor, breadcrumb as
  // before. Still no Organization unless the registry is ready, and no author:
  // none exists, and an invented byline is fabrication with a schema.
  const jsonLd = graph(
    websiteNode(config),
    articleNode(config, content, contentPath(config, content)),
    breadcrumbNode,
  );

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

        {/* Conditional blocks (2026-09-03): each renders only what it has. */}
        <SourcesBlock sources={sources} />
        <CtaBlock
          config={config}
          locale={locale}
          hasPriceEvidence={answers.length > 0}
        />
        <TrustSection hasSources={sources.length > 0} />
      </article>

      {jsonLd ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd }}
        />
      ) : null}
    </>
  );
}
