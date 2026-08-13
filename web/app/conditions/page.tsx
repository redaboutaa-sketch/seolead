import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Conditions",
  robots: { index: false, follow: false },
};

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
