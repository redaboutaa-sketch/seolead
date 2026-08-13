import type { Metadata } from "next";

import { getSiteConfig } from "@/lib/api";

export const metadata: Metadata = {
  title: "Confidentialité",
  robots: { index: false, follow: false },
};

/**
 * No privacy policy text is generated. What is stated here is only what this
 * implementation verifiably does; the legal document itself is owner/counsel work,
 * and a plausible-sounding generated policy would be a liability wearing the shape
 * of compliance.
 */
export default async function PrivacyPage() {
  const config = await getSiteConfig();
  return (
    <div className="container page">
      <h1>Confidentialité</h1>

      <div className="notice notice--placeholder">
        <p>
          <strong>Texte légal en attente.</strong> La politique de confidentialité
          définitive doit être rédigée ou validée par le propriétaire du site et son
          conseil. Aucun texte juridique n&apos;a été généré automatiquement.
        </p>
      </div>

      <h2>Ce que cette implémentation fait réellement</h2>
      <ul>
        <li>
          Les données du formulaire sont enregistrées dans la base de données de ce
          site et ne sont transmises à aucun système tiers.
        </li>
        <li>
          Le consentement au traitement est enregistré avec sa version
          (<code>{config?.legal.consent_version ?? "—"}</code>), sa date et la page
          d&apos;origine.
        </li>
        <li>
          Le consentement marketing est distinct et facultatif. Aucune case
          n&apos;est pré-cochée.
        </li>
        <li>
          Aucun outil de mesure tiers n&apos;est chargé. Les événements de parcours
          sont enregistrés en première partie, sans identifiant publicitaire.
        </li>
        <li>
          L&apos;adresse IP n&apos;est pas conservée&nbsp;: elle sert uniquement,
          sous forme de hachage éphémère, à limiter les envois automatisés.
        </li>
      </ul>

      <h2>Responsable du traitement</h2>
      <p>
        {config?.legal.data_controller ??
          "À compléter par le propriétaire du site."}
      </p>
    </div>
  );
}
