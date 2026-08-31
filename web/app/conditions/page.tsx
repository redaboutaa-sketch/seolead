import type { Metadata } from "next";

import { getSiteConfig } from "@/lib/api";
import { pageMetadata } from "@/lib/metadata";

// `noindex: true` stays hardcoded: a page whose body says « texte légal en
// attente » must never reach an index, whatever the site-wide gate does.
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  return pageMetadata({
    config,
    title: "Conditions",
    description:
      "Conditions d'utilisation du site Mon Projet Solaire. Le texte légal " +
      "est en attente de validation par le propriétaire du site.",
    path: "/conditions",
    noindex: true,
  });
}

export default function TermsPage() {
  return (
    <div className="container page">
      <h1>Conditions</h1>
      <div className="notice notice--placeholder">
        <p>
          <strong>Texte légal en attente.</strong> Les conditions d&apos;utilisation
          doivent être fournies ou validées par le propriétaire du site. Rien
          n&apos;a été généré ici.
        </p>
      </div>
    </div>
  );
}
