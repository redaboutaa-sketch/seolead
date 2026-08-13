import Link from "next/link";

import { CtaBlock, TrustSection } from "@/components/Cta";
import { getSiteConfig, listPublished } from "@/lib/api";
import { contentPath, isKnownRoute, localizedPath } from "@/lib/site";

export const revalidate = 300;

export default async function Home() {
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  const published = await listPublished(locale);

  return (
    <>
      <section className="container hero">
        <h1>Panneaux solaires en Belgique&nbsp;: des chiffres sourcés, pas des promesses</h1>
        <p className="hero__lede">
          Nous publions ce que les sources disent réellement du coût d&apos;une
          installation photovoltaïque, avec la base de chaque prix et son
          traitement TVA quand ils sont précisés — et nous le disons quand ils ne
          le sont pas.
        </p>
        <div className="cta-actions">
          {isKnownRoute(config, "/demande-etude") ? (
            <Link className="button" href={localizedPath(config, locale, "/demande-etude")}>
              {config?.conversion.primary_cta_label ?? "Demander une estimation"}
            </Link>
          ) : null}
          {isKnownRoute(config, "/outils/estimation-solaire") ? (
            <Link
              className="button button--secondary"
              href={localizedPath(config, locale, "/outils/estimation-solaire")}
            >
              Cadrer mon projet
            </Link>
          ) : null}
        </div>
      </section>

      <div className="container">
        {published.length > 0 ? (
          <section className="section" aria-labelledby="pages">
            <h2 id="pages">Nos pages</h2>
            <div className="card-grid">
              {published.map((item) => (
                <article className="card" key={`${item.locale}/${item.slug}`}>
                  <h3>
                    <Link href={contentPath(config, item)}>{item.title}</Link>
                  </h3>
                  {item.meta.description ? <p>{item.meta.description}</p> : null}
                </article>
              ))}
            </div>
          </section>
        ) : (
          <div className="notice notice--placeholder">
            <p>
              <strong>Aucune page n&apos;est encore publiée.</strong> Les contenus
              validés attendent la décision de publication du propriétaire du site.
            </p>
          </div>
        )}

        <TrustSection />
        <CtaBlock config={config} locale={locale} />
      </div>
    </>
  );
}
