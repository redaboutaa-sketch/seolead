import Link from "next/link";

import { brandName, knownRoutesForLocale, localizedPath } from "@/lib/site";
import type { PublishedContentDTO, SiteConfigDTO } from "@/lib/types";

const NAV_LABELS: Record<string, Record<string, string>> = {
  fr: {
    "/": "Accueil",
    "/prix-panneaux-solaires-belgique": "Prix",
    "/rentabilite-panneaux-solaires-belgique": "Rentabilité",
    "/outils/estimation-solaire": "Estimation",
    "/demande-etude": "Demander une étude",
  },
  nl: { "/": "Home" },
  en: { "/": "Home" },
};

/**
 * The wordmark.
 *
 * A drawn mark rather than a logo file, because the owner has not supplied a
 * logo — `OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md` lists it under RECOMMENDED. It is
 * built from the same sun-over-roof idea as `public/favicon.svg` so the two do
 * not diverge, and it is replaced wholesale the day a real logo arrives.
 */
function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      className="site-header__mark"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="14" fill="var(--brand)" />
      <circle cx="32" cy="23" r="8" fill="var(--solar)" />
      <path
        d="M32 8v5M32 33v5M17 23h5M42 23h5M21.4 12.4l3.5 3.5M39.1 30.1l3.5 3.5M42.6 12.4l-3.5 3.5M24.9 30.1l-3.5 3.5"
        stroke="var(--solar)"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path d="M12 48 32 36l20 12v6H12z" fill="var(--brand-contrast)" />
      <path d="M18 49h28" stroke="var(--brand)" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function StagingBanner({ config }: { config: SiteConfigDTO | null }) {
  if (!config || config.indexable) return null;
  return (
    <div className="staging-banner" role="status">
      <div className="container container--wide">
        <strong>Environnement de préproduction</strong> — contenu non public,
        indexation désactivée. Marque et coordonnées à confirmer.
      </div>
    </div>
  );
}

/**
 * The route list in `solar_be.yaml` declares which paths the site MAY link to.
 * For `TOOL` and `CONVERSION` routes that is the same thing as which paths
 * exist, because those are application routes. For `LANDING_PAGE` routes it is
 * not: their existence depends on the owner having published the content.
 *
 * The header treated the two as identical and shipped a link to
 * `/prix-panneaux-solaires`, which returns 404 — the published price page lives
 * at `prix-panneaux-solaires-belgique`. The mechanism whose stated purpose is
 * that "a link cannot ship pointing at a page that does not exist" was doing
 * exactly that, in the primary navigation, and spending an RSC prefetch on it
 * with every page load.
 *
 * A landing-page route is now rendered only when something is actually
 * published at that path. Nothing is invented to do it: the label still comes
 * from `NAV_LABELS`, and publication comes from `listPublished()`, the same
 * source the sitemap and the homepage's published-pages section already use.
 * The day the owner publishes at that path, the link reappears on its own.
 */
export function Header({
  config,
  locale,
  published = [],
}: {
  config: SiteConfigDTO | null;
  locale: string;
  published?: PublishedContentDTO[];
}) {
  const publishedPaths = new Set(
    published.map((item) => localizedPath(config, item.locale, `/${item.slug}`)),
  );
  const routes = knownRoutesForLocale(config, locale).filter((route) => {
    if (route.type === "LEGAL" || route.type === "CONVERSION") return false;
    if (route.type !== "LANDING_PAGE") return true;
    return publishedPaths.has(localizedPath(config, locale, route.path));
  });
  const labels = NAV_LABELS[locale] ?? {};
  const formPath = "/demande-etude";
  const hasForm = config?.routes.some((route) => route.path === formPath) ?? false;
  return (
    <header className="site-header">
      <div className="container container--wide site-header__inner">
        <Link className="site-header__brand" href={localizedPath(config, locale, "/")}>
          <BrandMark />
          {brandName(config)}
        </Link>
        <div className="site-header__actions">
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
          {/*
            The conversion route is promoted out of the nav list into a button:
            one visually primary action per viewport. Hidden below 52rem, where
            the sticky bar carries it instead.
          */}
          {hasForm ? (
            <Link
              className="button site-header__cta"
              href={localizedPath(config, locale, formPath)}
            >
              {config?.conversion.primary_cta_label ?? "Demander une estimation"}
            </Link>
          ) : null}
        </div>
      </div>
    </header>
  );
}

export function Footer({
  config,
  locale,
  published = [],
}: {
  config: SiteConfigDTO | null;
  locale: string;
  published?: PublishedContentDTO[];
}) {
  const all = knownRoutesForLocale(config, locale);
  const legal = all.filter((route) => route.type === "LEGAL");
  // Same rule as the header, for the same reason: the footer was shipping the
  // identical link to an unpublished landing page, so removing it from one place
  // and not the other would have fixed half a 404.
  const publishedPaths = new Set(
    published.map((item) => localizedPath(config, item.locale, `/${item.slug}`)),
  );
  const pages = all.filter((route) => {
    if (route.type === "LEGAL" || route.path === "/") return false;
    if (route.type !== "LANDING_PAGE") return true;
    return publishedPaths.has(localizedPath(config, locale, route.path));
  });
  const labels = NAV_LABELS[locale] ?? {};
  return (
    <footer className="site-footer">
      <div className="container container--wide">
        <div className="site-footer__grid">
          <div>
            <span className="site-footer__brand">
              <BrandMark size={26} />
              {brandName(config)}
              {config?.brand_name_is_placeholder ? " (provisoire)" : ""}
            </span>
            <p>
              Information sur le photovoltaïque résidentiel en Belgique, appuyée
              sur des sources consultées plutôt que sur des moyennes annoncées
              sans origine.
            </p>
            {/* L'opérateur, nommé sur chaque page dès que son identité est
                fournie : la marque est un service, l'entité derrière a un nom
                et un numéro — la distinction des entités est un invariant. */}
            {config?.organization.legal_name ? (
              <p className="site-footer__operator">
                {brandName(config)} est un service exploité par{" "}
                {config.organization.legal_name}
                {config.organization.registration_number
                  ? ` (n° ${config.organization.registration_number})`
                  : ""}
                .
              </p>
            ) : null}
          </div>

          {pages.length > 0 ? (
            <div>
              <h2>Le site</h2>
              <ul>
                {pages.map((route) => (
                  <li key={route.path}>
                    <Link href={localizedPath(config, locale, route.path)}>
                      {labels[route.path] ?? route.path.replace(/^\//, "")}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div>
            <h2>Contact &amp; mentions</h2>
            {/*
              Contact details are shown only when the owner has supplied them. An
              invented phone number on a lead-generation site is a lie that rings.
            */}
            {config?.contact.email || config?.contact.phone ? (
              <ul>
                {config?.contact.email ? (
                  <li>
                    <a href={`mailto:${config.contact.email}`}>{config.contact.email}</a>
                  </li>
                ) : null}
                {config?.contact.phone ? (
                  <li>
                    <a href={`tel:${config.contact.phone.replace(/\s/g, "")}`}>
                      {config.contact.phone}
                    </a>
                  </li>
                ) : null}
              </ul>
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
        </div>

        <div className="site-footer__legal">
          <p>
            {brandName(config)}
            {config?.brand_name_is_placeholder
              ? " — nom commercial provisoire, en attente de validation."
              : ""}
          </p>
        </div>
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
