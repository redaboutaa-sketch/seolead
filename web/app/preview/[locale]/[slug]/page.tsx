import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ContentView } from "@/app/[slug]/page";
import { getPreview, getSiteConfig } from "@/lib/api";

/**
 * The staging preview route.
 *
 * Never cached, never indexed, and it reaches an API endpoint that demands a
 * second secret. A crawler that somehow found this URL gets `noindex, nofollow`
 * from metadata and a 404 from the API, which is two independent refusals.
 */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
  title: "Aperçu (préproduction)",
};

export default async function PreviewPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const config = await getSiteConfig();
  const content = await getPreview(locale, slug);
  if (!content) notFound();

  return (
    <>
      <div className="staging-banner" role="status">
        <div className="container">
          <strong>Aperçu</strong> — version {content.version}, état {content.state}.
          Cette page n&apos;est pas publiée.
        </div>
      </div>
      <ContentView config={config} locale={locale} content={content} />
    </>
  );
}
