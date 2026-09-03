import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ContentView } from "@/app/[slug]/page";
import { getDraftPreview, getSiteConfig } from "@/lib/api";

/**
 * Owner review of a draft that is not approved and therefore cannot be staged.
 *
 * Never cached, never indexed, and behind the preview token. Viewing this page
 * changes nothing: approval remains a separate, deliberate act.
 */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
  title: "Relecture (brouillon)",
};

export default async function DraftPreviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const config = await getSiteConfig();
  const content = await getDraftPreview(id);
  if (!content) notFound();

  const gate = (content as unknown as { gate?: { reasons?: string[] } }).gate;
  const fingerprint = content.fingerprint;

  return (
    <>
      <div className="staging-banner" role="status">
        <div className="container">
          <strong>Relecture</strong> — brouillon non approuvé, non publiable en
          l&apos;état.
          {gate?.reasons?.length ? ` Blocage : ${gate.reasons.join(" ; ")}.` : ""}
          {/* The render being read, named. `content approve --fingerprint`
              takes exactly this value; any later change to the render
              changes it, and the approval with it. */}
          {fingerprint ? (
            <>
              {" "}
              Empreinte du rendu&nbsp;: <code>{fingerprint}</code>
            </>
          ) : null}
        </div>
      </div>
      <ContentView
        config={config}
        locale={content.locale}
        content={content}
      />
    </>
  );
}
