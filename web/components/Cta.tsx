import Link from "next/link";

import { isKnownRoute, localizedPath } from "@/lib/site";
import type { SiteConfigDTO } from "@/lib/types";

/**
 * The conversion block.
 *
 * No countdown, no scarcity, no "3 places restantes". The offer is an estimate;
 * the honest reason to act is that the visitor wants one. Manufactured urgency on
 * a page whose whole credibility rests on sourced evidence would undo the evidence.
 */
export function CtaBlock({
  config,
  locale,
  heading = "Obtenir une estimation pour votre toiture",
  body,
}: {
  config: SiteConfigDTO | null;
  locale: string;
  heading?: string;
  body?: string;
}) {
  const formPath = "/demande-etude";
  const toolPath = "/outils/estimation-solaire";
  return (
    <section className="cta-block" aria-labelledby="cta-heading">
      <h2 id="cta-heading">{heading}</h2>
      <p>
        {body ??
          "Les fourchettes ci-dessus viennent de sources publiées. Le prix de votre installation dépend de votre toiture, de votre consommation et du matériel retenu — quelques questions suffisent pour cadrer le projet."}
      </p>
      <div className="cta-actions">
        {isKnownRoute(config, formPath) ? (
          <Link className="button" href={localizedPath(config, locale, formPath)}>
            {config?.conversion.primary_cta_label ?? "Demander une estimation"}
          </Link>
        ) : null}
        {isKnownRoute(config, toolPath) ? (
          <Link
            className="button button--secondary"
            href={localizedPath(config, locale, toolPath)}
          >
            Cadrer mon projet en 2 minutes
          </Link>
        ) : null}
      </div>
    </section>
  );
}

export function TrustSection() {
  return (
    <section className="section" aria-labelledby="methode">
      <h2 id="methode">Comment ces informations sont établies</h2>
      <div className="card-grid">
        <article className="card">
          <h3>Chiffres sourcés</h3>
          <p>
            Chaque montant affiché provient d&apos;une source publiée et consultée,
            avec sa base de calcul et son traitement TVA lorsqu&apos;ils sont
            précisés.
          </p>
        </article>
        <article className="card">
          <h3>Incertitude affichée</h3>
          <p>
            Quand une source ne précise pas la TVA ou la base d&apos;un prix, nous
            l&apos;indiquons au lieu de le supposer.
          </p>
        </article>
        <article className="card">
          <h3>Pas de moyenne inventée</h3>
          <p>
            Une fourchette relevée dans une source reste une observation. Elle
            n&apos;est jamais présentée comme un prix moyen belge.
          </p>
        </article>
      </div>
    </section>
  );
}
