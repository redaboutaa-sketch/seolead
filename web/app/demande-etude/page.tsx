import type { Metadata } from "next";

import { IconCheck } from "@/components/home/Icons";
import { LeadForm } from "@/components/LeadForm";
import { getSiteConfig } from "@/lib/api";

export const metadata: Metadata = {
  title: "Demander une estimation",
  description:
    "Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

/**
 * The conversion page.
 *
 * Only the shell around the form changed: an aside that tells the visitor what
 * they are about to spend and what they get for it, which is the standard remedy
 * for the drop-off a bare multi-step form produces.
 *
 * `LeadForm` itself, its steps, its fields, its validation and its payload are
 * untouched — US-SL-01 is presentation-only and this page is the seam.
 */
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

  const steps = config.conversion.form_steps ?? [];

  return (
    <div className="container container--wide page">
      <h1>Obtenir une estimation pour votre installation</h1>
      <p className="hero__lede">
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

      <div className="form-shell">
        <aside className="form-aside">
          <h2>Les {steps.length} étapes</h2>
          <ul>
            {steps.map((step) => (
              <li key={step.key}>
                <IconCheck size={20} />
                <span>
                  <strong>{step.title}</strong>
                  {step.description ? <> — {step.description}</> : null}
                </span>
              </li>
            ))}
          </ul>
          <p>
            Les questions personnelles arrivent en dernier, et celles sur votre
            consommation sont facultatives.
          </p>
        </aside>

        <div>
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
      </div>
    </div>
  );
}
