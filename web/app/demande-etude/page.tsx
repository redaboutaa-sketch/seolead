import type { Metadata } from "next";

import { LeadForm } from "@/components/LeadForm";
import { getSiteConfig } from "@/lib/api";

export const metadata: Metadata = {
  title: "Demander une estimation",
  description:
    "Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function RequestPage() {
  const config = await getSiteConfig();
  if (!config) {
    return (
      <div className="container page">
        <h1>Formulaire indisponible</h1>
        <p>La configuration du site n&apos;a pas pu être chargée.</p>
      </div>
    );
  }

  return (
    <div className="container page">
      <h1>Obtenir une estimation pour votre installation</h1>
      <p>
        Les questions ci-dessous servent à cadrer votre projet. Aucune donnée
        n&apos;est transmise à un tiers&nbsp;: la demande est enregistrée pour
        qu&apos;un interlocuteur vous réponde.
      </p>

      {!config.legal.reviewed ? (
        <div className="notice notice--placeholder">
          <p>
            <strong>Mentions légales en attente.</strong> Le texte définitif de la
            politique de confidentialité doit être fourni ou validé par le
            propriétaire du site avant toute mise en ligne publique.
          </p>
        </div>
      ) : null}

      <LeadForm
        config={config}
        locale={config.default_language}
        conversionType={config.conversion.primary_cta}
        attribution={{
          landing_path: "/demande-etude",
          page_path: "/demande-etude",
          channel: "direct",
          cta: config.conversion.primary_cta,
        }}
      />
    </div>
  );
}
