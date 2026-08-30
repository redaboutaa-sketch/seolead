import { IconCheck } from "@/components/home/Icons";
import { LeadForm } from "@/components/LeadForm";
import { getSiteConfig } from "@/lib/api";
import { localizedText, localizedPath } from "@/lib/site";

/**
 * The conversion page's body, shared by every locale route.
 *
 * One component rather than one copy per locale, so the two pages cannot
 * diverge structurally: `/demande-etude` and `/nl/demande-etude` differ only by
 * the locale they pass. The locale then travels the whole chain — LeadForm
 * submits it as `language`, the API validates it against
 * `supported_languages`, and it lands in `lead_attribution.language` and in the
 * export payload's `attribution.locale`.
 *
 * The `nl` copy below is a PLACEHOLDER marked « À TRADUIRE PAR UN NATIF »,
 * with the French text as the visible fallback. No machine translation, ever.
 */

interface PageCopy {
  heading: string;
  lede: string;
  legalPending: string;
  legalPendingLead: string;
  stepsTitle: (count: number) => string;
  aside: string;
  unavailableTitle: string;
  unavailableBody: string;
}

const NL_TODO = "[NL — À TRADUIRE PAR UN NATIF] ";

const FR_COPY: PageCopy = {
  heading: "Obtenir une estimation pour votre installation",
  // Phrase mise à jour le 2026-08-30 avec la politique v1.1 : la transmission
  // au partenaire existe désormais, conditionnée au consentement explicite —
  // affirmer « aucun tiers » serait devenu faux.
  lede:
    "Les questions ci-dessous servent à cadrer votre projet. Vos données ne sont transmises à notre partenaire installateur qu'avec votre consentement explicite ; la demande est enregistrée pour qu'un interlocuteur vous réponde.",
  legalPendingLead: "Mentions légales en attente.",
  legalPending:
    "Le texte définitif de la politique de confidentialité doit être fourni ou validé par le propriétaire du site avant toute mise en ligne publique.",
  stepsTitle: (count) => `Les ${count} étapes`,
  aside:
    "Les questions personnelles arrivent en dernier, et celles sur votre consommation sont facultatives.",
  unavailableTitle: "Formulaire indisponible",
  unavailableBody: "La configuration du site n'a pas pu être chargée.",
};

const COPY: Record<string, PageCopy> = {
  fr: FR_COPY,
  nl: {
    heading: `${NL_TODO}Obtenir une estimation pour votre installation`,
    lede: `${NL_TODO}Les questions ci-dessous servent à cadrer votre projet. Vos données ne sont transmises à notre partenaire installateur qu'avec votre consentement explicite ; la demande est enregistrée pour qu'un interlocuteur vous réponde.`,
    legalPendingLead: `${NL_TODO}Mentions légales en attente.`,
    legalPending: `${NL_TODO}Le texte définitif de la politique de confidentialité doit être fourni ou validé par le propriétaire du site avant toute mise en ligne publique.`,
    stepsTitle: (count) => `${NL_TODO}Les ${count} étapes`,
    aside: `${NL_TODO}Les questions personnelles arrivent en dernier, et celles sur votre consommation sont facultatives.`,
    unavailableTitle: `${NL_TODO}Formulaire indisponible`,
    unavailableBody: `${NL_TODO}La configuration du site n'a pas pu être chargée.`,
  },
};

export async function RequestStudyPage({ locale }: { locale: string }) {
  const config = await getSiteConfig();
  const copy = COPY[locale] ?? FR_COPY;
  if (!config) {
    return (
      <div className="container page">
        <h1>{copy.unavailableTitle}</h1>
        <p>{copy.unavailableBody}</p>
      </div>
    );
  }

  const steps = config.conversion.form_steps ?? [];
  const pagePath = localizedPath(config, locale, "/demande-etude");

  return (
    <div className="container container--wide page">
      <h1>{copy.heading}</h1>
      <p className="hero__lede">{copy.lede}</p>

      {!config.legal.reviewed ? (
        <div className="notice notice--placeholder">
          <p>
            <strong>{copy.legalPendingLead}</strong> {copy.legalPending}
          </p>
        </div>
      ) : null}

      <div className="form-shell">
        <aside className="form-aside">
          <h2>{copy.stepsTitle(steps.length)}</h2>
          <ul>
            {steps.map((step) => (
              <li key={step.key}>
                <IconCheck size={20} />
                <span>
                  <strong>{localizedText(step, locale, "title")}</strong>
                  {localizedText(step, locale, "description") ? (
                    <> — {localizedText(step, locale, "description")}</>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
          <p>{copy.aside}</p>
        </aside>

        <div>
          <LeadForm
            config={config}
            locale={locale}
            conversionType={config.conversion.primary_cta}
            attribution={{
              landing_path: pagePath,
              page_path: pagePath,
              channel: "direct",
              cta: config.conversion.primary_cta,
            }}
          />
        </div>
      </div>
    </div>
  );
}
