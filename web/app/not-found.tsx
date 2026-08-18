import Link from "next/link";

export default function NotFound() {
  return (
    <div className="container page">
      <p className="eyebrow">Erreur 404</p>
      <h1>Page introuvable</h1>
      <p className="hero__lede">
        Cette page n&apos;existe pas ou n&apos;est pas encore publiée.
      </p>
      <Link className="button button--large" href="/">
        Retour à l&apos;accueil
      </Link>
    </div>
  );
}
