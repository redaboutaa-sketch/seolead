import Link from "next/link";

export default function NotFound() {
  return (
    <div className="container page">
      <h1>Page introuvable</h1>
      <p>
        Cette page n&apos;existe pas ou n&apos;est pas encore publiée.
      </p>
      <Link className="button" href="/">
        Retour à l&apos;accueil
      </Link>
    </div>
  );
}
