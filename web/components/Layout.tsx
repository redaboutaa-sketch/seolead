import Link from "next/link";

import { brandName, knownRoutesForLocale, localizedPath } from "@/lib/site";
import type { SiteConfigDTO } from "@/lib/types";

const NAV_LABELS: Record<string, Record<string, string>> = {
  fr: {
    "/": "Accueil",
    "/prix-panneaux-solaires": "Prix",
    "/outils/estimation-solaire": "Estimation",
    "/demande-etude": "Demander une étude",
  },
  nl: { "/": "Home" },
  en: { "/": "Home" },
};

export function StagingBanner({ config }: { config: SiteConfigDTO | null }) {
  if (!config || config.indexable) return null;
  return (
    <div className="staging-banner" role="status">
      <div className="container">
        <strong>Environnement de préproduction</strong> — contenu non public,
        indexation désactivée. Marque et coordonnées à confirmer.
      </div>
    </div>
  );
}

export function Header({ config, locale }: { config: SiteConfigDTO | null; locale: string }) {
  const routes = knownRoutesForLocale(config, locale).filter(
    (route) => route.type !== "LEGAL",
  );
  const labels = NAV_LABELS[locale] ?? {};
  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <Link className="site-header__brand" href={localizedPath(config, locale, "/")}>
          {brandName(config)}
        </Link>
        <nav className="site-nav" aria-label="Navigation principale">
          <ul>
            {routes.map((route) => (
              <li key={route.path}>
                <Link href={localizedPath(config, locale, route.path)}>
                  {labels[route.path] ?? route.path.replace(/^\//, "")}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}

export function Footer({ config, locale }: { config: SiteConfigDTO | null; locale: string }) {
  const legal = knownRoutesForLocale(config, locale).filter(
    (route) => route.type === "LEGAL",
  );
  return (
    <footer className="site-footer">
      <div className="container">
        <p>
          {brandName(config)}
          {config?.brand_name_is_placeholder
            ? " — nom commercial provisoire, en attente de validation."
            : ""}
        </p>
        {/*
          Contact details are shown only when the owner has supplied them. An
          invented phone number on a lead-generation site is a lie that rings.
        */}
        {config?.contact.email || config?.contact.phone ? (
          <p>
            {config?.contact.email ? <span>{config.contact.email} </span> : null}
            {config?.contact.phone ? <span>{config.contact.phone}</span> : null}
          </p>
        ) : (
          <p>Coordonnées commerciales à confirmer par le propriétaire du site.</p>
        )}
        {legal.length > 0 ? (
          <ul>
            {legal.map((route) => (
              <li key={route.path}>
                <Link href={localizedPath(config, locale, route.path)}>
                  {route.path === config?.legal.privacy_policy_path
                    ? "Confidentialité"
                    : "Conditions"}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </footer>
  );
}

export function Breadcrumbs({
  items,
}: {
  items: { label: string; href?: string }[];
}) {
  if (items.length < 2) return null;
  return (
    <nav className="breadcrumbs container" aria-label="Fil d'Ariane">
      <ol>
        {items.map((item, index) => (
          <li key={index}>
            {item.href && index < items.length - 1 ? (
              <Link href={item.href}>{item.label}</Link>
            ) : (
              <span aria-current="page">{item.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
