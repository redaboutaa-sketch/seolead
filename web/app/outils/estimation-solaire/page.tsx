import type { Metadata } from "next";

import { IconCheck } from "@/components/home/Icons";
import { LeadForm } from "@/components/LeadForm";
import Link from "next/link";

import { getSiteConfig } from "@/lib/api";
import { pageMetadata } from "@/lib/metadata";
import { FINANCING_PATH, financingLandingVisible, localizedPath } from "@/lib/site";

// Robots follow the site-wide gate, like /demande-etude: the declared route
// table feeds the sitemap, and a hardcoded noindex would contradict it at
// flip time.
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  return pageMetadata({
    config,
    title: "Cadrer votre projet solaire",
    description:
      "Un questionnaire de qualification qui décrit votre projet — sans estimation financière tant qu'aucun calcul défendable n'est implémenté.",
    path: "/outils/estimation-solaire",
  });
}

export const dynamic = "force-dynamic";

/**
 * A qualification tool, deliberately not a simulator.
 *
 * A savings figure needs irradiation data, roof geometry, a consumption profile
 * and current tariffs. None of those is implemented, so this page qualifies the
 * project and says what it cannot yet tell you. Showing an invented payback period
 * would be exactly the failure the evidence pipeline exists to prevent, moved from
 * the content layer into a calculator.
 */
export default async function EstimationTool() {
  const config = await getSiteConfig();
  if (!config) {
    return (
      <div className="container page">
        <h1>Outil indisponible</h1>
      </div>
    );
  }

  const steps = config.conversion.form_steps ?? [];

  return (
    <div className="container container--wide page">
      <h1>Cadrer votre projet solaire</h1>
      <p className="hero__lede">
        Cet outil décrit votre projet et prépare une estimation faite par un
        interlocuteur. Il ne calcule pas d&apos;économies ni de temps de retour.
      </p>

      <div className="form-shell">
        <aside className="form-aside">
          <div className="notice">
            <p>
              <strong>Pourquoi aucun chiffre d&apos;économies ici&nbsp;?</strong> Une
              estimation de rentabilité dépend de l&apos;ensoleillement de votre
              adresse, de l&apos;orientation et de l&apos;inclinaison du toit, de
              votre profil de consommation et des tarifs en vigueur. Tant que ces
              données ne sont pas intégrées de façon vérifiable, afficher un
              montant serait une invention.
            </p>
          </div>
          <ul>
            {steps.map((step) => (
              <li key={step.key}>
                <IconCheck size={20} />
                <span>
                  <strong>{step.title}</strong>
                </span>
              </li>
            ))}
          </ul>
          {/* Lien naturel vers la landing financement — même porte que la
              landing elle-même : jamais un lien vers une page qui 404. */}
          {financingLandingVisible(config) ? (
            <div className="notice">
              <p>
                <strong>Pas d&apos;épargne à mobiliser&nbsp;?</strong> Selon
                votre situation, différentes solutions de financement peuvent
                être étudiées.{" "}
                <Link href={localizedPath(config, config.default_language, FINANCING_PATH)}>
                  Ce que « sans apport » veut vraiment dire
                </Link>
              </p>
            </div>
          ) : null}
        </aside>

        <div>
          <LeadForm
            config={config}
            locale={config.default_language}
            conversionType="TOOL_COMPLETION"
            attribution={{
              landing_path: "/outils/estimation-solaire",
              page_path: "/outils/estimation-solaire",
              channel: "direct",
              cta: "TOOL_COMPLETION",
            }}
          />
        </div>
      </div>
    </div>
  );
}
