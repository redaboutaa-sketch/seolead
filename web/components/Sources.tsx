import type { SourceRef } from "@/lib/types";

/**
 * The sources behind the figures on a content page.
 *
 * The « méthode » block below promises « chaque montant affiché provient
 * d'une source publiée ». Until 2026-09-03 nothing on the page let a reader
 * check that: the article on payback stated « rentabilisée au bout de 5 ans »,
 * no source carried the figure, and the page looked exactly like one whose
 * every figure was sourced. This block is what makes the promise checkable.
 *
 * It renders NOTHING when there is nothing to list — and the caller renders
 * the promise only when this block has something to show. A template block
 * that announces data it does not have is a claim, not a layout.
 *
 * No link, no URL. An official authority is named (its host, as text). A
 * commercial or specialist source is described by its tier: naming it would
 * be advertising a competitor on a page about prices.
 */

const TIER_LABEL: Record<string, string> = {
  OFFICIAL: "Source officielle",
  SPECIALIST: "Source spécialisée",
  COMMERCIAL: "Source commerciale",
  COMMUNITY: "Source communautaire",
};

const REGION_LABEL: Record<string, string> = {
  "BE-WAL": "Wallonie",
  "BE-BRU": "Bruxelles",
  "BE-VLG": "Flandre",
  BE: "Belgique",
};

function tierLabel(tier: string): string {
  return TIER_LABEL[tier] ?? "Source";
}

function regionLabel(region: string | null): string | null {
  if (!region) return null;
  return REGION_LABEL[region] ?? null;
}

export function sourceLine(source: SourceRef): string {
  const head = source.name ?? tierLabel(source.tier);
  const parts: string[] = [];
  if (source.name) parts.push(tierLabel(source.tier).toLowerCase());
  const region = regionLabel(source.region);
  if (region) parts.push(region);
  parts.push(source.date ? `consultée, datée du ${source.date}` : "non datée");
  return `${head} (${parts.join(", ")})`;
}

export function SourcesBlock({ sources }: { sources: SourceRef[] | undefined }) {
  if (!sources || sources.length === 0) return null;
  return (
    <section className="section sources" aria-labelledby="sources">
      <h2 id="sources">Sources des chiffres de cette page</h2>
      <ul className="sources__list">
        {sources.map((source, index) => (
          <li key={index} className="sources__item">
            <span className="sources__name">{sourceLine(source)}</span>
            {source.figures.length > 0 ? (
              <span className="sources__figures">
                {" "}
                — porte&nbsp;: {source.figures.join(", ")}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="evidence-note">
        Aucun lien n&apos;est fourni vers ces sources&nbsp;: elles sont nommées
        pour que vous puissiez les consulter vous-même. Un chiffre qui ne figure
        dans aucune d&apos;elles n&apos;a pas sa place sur cette page.
      </p>
    </section>
  );
}
