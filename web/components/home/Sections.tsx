import Link from "next/link";

import { FINANCING_PATH, financingLandingVisible, isKnownRoute, localizedPath } from "@/lib/site";
import type { PublishedContentDTO, SiteConfigDTO } from "@/lib/types";

import { HeroVisual } from "./HeroVisual";
import {
  IconCheck,
  IconClipboard,
  IconHouse,
  IconPerson,
  IconShield,
  IconSource,
  IconSun,
  IconUnknown,
} from "./Icons";

/**
 * Homepage sections.
 *
 * Every one of these is a server component with no interactivity, so the
 * homepage still ships zero client JavaScript — the performance criterion in
 * US-SL-01 (§10) depends on that staying true.
 *
 * The copy rule that governs this whole file: nothing here asserts anything the
 * project does not already hold authority for. No review, no certification, no
 * partner, no savings figure, no install count, no subsidy amount, no price.
 * Where a sentence makes a factual claim, its source is named in a comment.
 */

const FORM_PATH = "/demande-etude";
const TOOL_PATH = "/outils/estimation-solaire";

type Ctx = { config: SiteConfigDTO | null; locale: string };

/** The canonical primary label. It is configuration (`conversion.primary_cta_label`), not copy. */
function primaryLabel(config: SiteConfigDTO | null): string {
  return config?.conversion.primary_cta_label ?? "Demander une estimation";
}

export function PrimaryCta({
  config,
  locale,
  className = "button button--large",
}: Ctx & { className?: string }) {
  if (!isKnownRoute(config, FORM_PATH)) return null;
  return (
    <Link className={className} href={localizedPath(config, locale, FORM_PATH)} data-cta="primary">
      {primaryLabel(config)}
    </Link>
  );
}

function SecondaryCta({ config, locale }: Ctx) {
  if (!isKnownRoute(config, TOOL_PATH)) return null;
  return (
    <Link
      className="button button--link button--large"
      href={localizedPath(config, locale, TOOL_PATH)}
    >
      Cadrer mon projet
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M5 12h13M13 6l6 6-6 6" />
      </svg>
    </Link>
  );
}

/* ── Hero ───────────────────────────────────────────────────────────────── */

export function Hero({ config, locale }: Ctx) {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="container container--wide hero__inner">
        <div>
          <p className="eyebrow">Photovoltaïque résidentiel · Belgique</p>
          <h1 className="hero__title" id="hero-title">
            Votre projet solaire, cadré sans promesse en l&apos;air
          </h1>
          <p className="hero__lede">
            Quelques questions sur votre logement et votre toiture suffisent à
            décrire votre projet. Et les chiffres que nous publions viennent de
            sources consultées&nbsp;— quand une source ne précise pas, nous le
            disons plutôt que de le supposer.
          </p>
          {/* Positionnement financement (P1.2) — secondaire et conditionnel :
              « selon votre situation », « peuvent être étudiées ». Jamais une
              promesse ; la page dédiée porte le sujet, le hero le signale. */}
          {financingLandingVisible(config) ? (
            <p className="hero__financing">
              Pas d&apos;épargne à mobiliser&nbsp;? Selon votre situation,
              différentes solutions de financement peuvent être étudiées.{" "}
              <Link href={localizedPath(config, locale, FINANCING_PATH)}>
                Découvrir les solutions sans apport
              </Link>
            </p>
          ) : null}
          <div className="hero__actions">
            <PrimaryCta config={config} locale={locale} />
            <SecondaryCta config={config} locale={locale} />
          </div>
          {/*
            All three are verifiable today. "Gratuit" and "sans engagement":
            the product contains no payment path and no contract. The third is
            quoted from the owner-approved privacy text at /confidentialite
            ("droit de retirer votre consentement à tout moment").

            An earlier draft read "vos données restent en Belgique". It was
            removed at the SPEC CONSISTENCY gate: the privacy text names a French
            controller and permits technical subcontractors, so the claim would
            have been fabricated.
          */}
          <ul className="hero__reassurance">
            <li>
              <IconCheck size={18} />
              Gratuit
            </li>
            <li>
              <IconCheck size={18} />
              Sans engagement
            </li>
            <li>
              <IconCheck size={18} />
              Consentement retirable à tout moment
            </li>
          </ul>
        </div>
        <div className="hero__visual">
          <HeroVisual />
        </div>
      </div>
    </section>
  );
}

/* ── Assurance strip ────────────────────────────────────────────────────── */

/**
 * Where a competitor puts star ratings and installer logos.
 *
 * This site has neither, and inventing them is refused. What it has instead is
 * three properties that are true, unusual in the category, and checkable in this
 * repository — so those are what the strip says.
 */
export function Assurances() {
  return (
    <section className="assurances" aria-label="Nos engagements">
      <div className="container container--wide">
        <ul>
          <li>
            <IconSource size={22} />
            <span>
              <strong>Chiffres sourcés</strong>
              Chaque montant publié provient d&apos;une source consultée, avec sa
              base et son traitement TVA lorsqu&apos;ils sont précisés.
            </span>
          </li>
          <li>
            <IconUnknown size={22} />
            <span>
              <strong>Incertitude affichée</strong>
              Quand une source ne précise pas la base d&apos;un prix ou la TVA,
              nous l&apos;indiquons au lieu de le supposer.
            </span>
          </li>
          <li>
            <IconShield size={22} />
            <span>
              <strong>Consentement maîtrisé</strong>
              Deux cases distinctes, aucune pré-cochée, et un consentement que
              vous pouvez retirer à tout moment.
            </span>
          </li>
        </ul>
      </div>
    </section>
  );
}

/* ── Benefits ───────────────────────────────────────────────────────────── */

export function Benefits() {
  return (
    <section className="band" aria-labelledby="benefices">
      <div className="container container--wide">
        <div className="section-head">
          <p className="eyebrow">Ce que vous y gagnez</p>
          <h2 id="benefices">Décider en connaissance de cause, pas sous pression</h2>
          <p>
            Un projet photovoltaïque se joue sur votre toiture, votre
            consommation et votre échéance. Le reste n&apos;est que du bruit.
          </p>
        </div>
        <div className="card-grid">
          <article className="card">
            <span className="card__icon">
              <IconHouse size={24} />
            </span>
            <h3>Savoir ce que votre toiture permet</h3>
            <p>
              Avant de comparer des devis, il faut savoir ce qui est possible chez
              vous. Orientation, type de toiture, type de logement&nbsp;: ce sont
              ces réponses qui cadrent le reste.
            </p>
          </article>
          <article className="card">
            <span className="card__icon card__icon--solar">
              <IconSun size={24} />
            </span>
            <h3>Ne pas partir d&apos;un chiffre inventé</h3>
            <p>
              Une fourchette relevée dans une source reste une observation. Elle
              n&apos;est jamais présentée ici comme un prix moyen belge, et aucune
              économie n&apos;est annoncée tant qu&apos;aucun calcul défendable ne
              la soutient.
            </p>
          </article>
          <article className="card">
            <span className="card__icon">
              <IconShield size={24} />
            </span>
            <h3>Garder la main sur vos données</h3>
            <p>
              Vos réponses servent à traiter votre demande. Le consentement au
              traitement et celui aux informations commerciales sont deux choses
              distinctes, et refuser le second ne bloque rien.
            </p>
          </article>
        </div>
      </div>
    </section>
  );
}

/* ── How it works ───────────────────────────────────────────────────────── */

/**
 * The real journey, not the category's.
 *
 * Competitors show a six-step *installation* sequence. This site does not
 * install anything, so showing one would describe work it does not perform.
 * These three steps are what actually happens, and step 1 mirrors the five form
 * steps declared in `config/sites/solar_be.yaml`.
 */
export function Process() {
  return (
    <section className="band band--tint" aria-labelledby="deroulement">
      <div className="container container--wide">
        <div className="section-head">
          <p className="eyebrow">Comment ça se passe</p>
          <h2 id="deroulement">Trois étapes, et vous savez à quoi vous en tenir</h2>
        </div>
        <ol className="steps">
          <li className="step">
            <h3>Vous décrivez votre projet</h3>
            <p>
              Cinq étapes courtes&nbsp;: votre logement, votre toiture, votre
              consommation, votre échéance, puis vos coordonnées. Les questions
              personnelles arrivent en dernier, pas en premier.
            </p>
          </li>
          <li className="step">
            <h3>Votre demande est qualifiée</h3>
            <p>
              Vos réponses sont structurées&nbsp;: type de bien, orientation de
              toiture, ordre de grandeur de consommation, échéance envisagée.
              C&apos;est ce qui permet de vous répondre utilement.
            </p>
          </li>
          <li className="step">
            <h3>Un interlocuteur revient vers vous</h3>
            <p>
              Votre demande est enregistrée pour qu&apos;un interlocuteur vous
              réponde avec une estimation adaptée à votre situation.
            </p>
          </li>
        </ol>
      </div>
    </section>
  );
}

/* ── Method / published proof ───────────────────────────────────────────── */

/**
 * Replaces the "savings visual" the brief proposed.
 *
 * There is no calculator and no defensible savings figure, so a savings section
 * could only be filled by inventing one. What the project genuinely has is a
 * method and, when the owner publishes them, evidence-backed pages. That is what
 * this section shows — and when nothing is published it says so, exactly as the
 * previous build did.
 */
export function Method({
  config,
  published,
}: {
  config: SiteConfigDTO | null;
  published: PublishedContentDTO[];
}) {
  return (
    <section className="band" aria-labelledby="methode">
      <div className="container container--wide">
        <div className="method">
          <div>
            <p className="eyebrow">Notre méthode</p>
            <h2 id="methode">D&apos;où viennent les chiffres que vous lisez ici</h2>
            <p>
              La plupart des pages sur le prix des panneaux solaires avancent une
              moyenne sans dire d&apos;où elle sort. Nous faisons l&apos;inverse.
            </p>
            <ul className="method__points">
              <li>
                <IconCheck size={20} />
                <span>
                  <strong>Une source, consultée.</strong> Chaque montant publié
                  renvoie à une source réellement lue, pas à une estimation
                  maison.
                </span>
              </li>
              <li>
                <IconCheck size={20} />
                <span>
                  <strong>Sa base et sa TVA.</strong> Un montant de 6&nbsp;000&nbsp;€
                  peut être un total, un tarif au kWc ou un prix au m². Nous
                  affichons ce que la source précise&nbsp;— et signalons ce
                  qu&apos;elle ne précise pas.
                </span>
              </li>
              <li>
                <IconCheck size={20} />
                <span>
                  <strong>Aucune moyenne fabriquée.</strong> Une fourchette
                  observée reste une observation. Elle n&apos;est jamais
                  requalifiée en prix moyen belge.
                </span>
              </li>
            </ul>
          </div>
          <div>
            {published.length > 0 ? (
              <>
                <h3>Nos pages publiées</h3>
                <ul className="pages-list">
                  {published.map((item) => (
                    <li key={`${item.locale}/${item.slug}`}>
                      <Link
                        className="page-link"
                        href={localizedPath(config, item.locale, `/${item.slug}`)}
                      >
                        <strong>{item.title}</strong>
                        {item.meta.description ? <span>{item.meta.description}</span> : null}
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <div className="notice notice--placeholder">
                <p>
                  <strong>Aucune page n&apos;est encore publiée.</strong> Les
                  contenus validés attendent la décision de publication du
                  propriétaire du site.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Qualification CTA ──────────────────────────────────────────────────── */

/**
 * The lead journey, made visually central.
 *
 * The five items are the five `conversion.form_steps` from
 * `config/sites/solar_be.yaml`, read from the configuration rather than
 * duplicated — so a step added in YAML appears here, and a step renamed cannot
 * silently disagree with the form the visitor then meets.
 */
export function QualificationCta({ config, locale }: Ctx) {
  const steps = config?.conversion.form_steps ?? [];
  return (
    <section className="band band--tint" aria-labelledby="qualification">
      <div className="container container--wide">
        <div className="qualif">
          <div>
            <p className="eyebrow">Votre demande</p>
            <h2 id="qualification">Ce qui vous sera demandé, avant de commencer</h2>
            <p>
              Rien d&apos;inutile, et rien de personnel avant la dernière étape.
              Vous pouvez revenir en arrière à tout moment, et les questions de
              consommation sont facultatives.
            </p>
            <div className="cta-actions">
              <PrimaryCta config={config} locale={locale} />
            </div>
          </div>
          <ol className="qualif__steps">
            {steps.map((step, index) => (
              <li key={step.key}>
                <span aria-hidden="true">{index + 1}</span>
                {step.title}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

/* ── FAQ ────────────────────────────────────────────────────────────────── */

/**
 * Six questions, each answerable from something that exists — the two
 * financing entries answer from the dedicated landing's validated copy, short
 * answer first, and none was added to round a number out. The 24-month figure is
 * the retention period stated in the owner-approved privacy text; the "no
 * savings figure" answer is the reasoning already published on
 * /outils/estimation-solaire.
 */
/**
 * The FAQ as DATA, because it now has two consumers that must never disagree:
 * the rendered `<details>` list below, and the FAQPage JSON-LD the homepage
 * emits. One structure, two projections — a schema whose answers drifted from
 * the visible page would be exactly the fabrication the JSON-LD module refuses.
 *
 * `answer` is plain text (what the schema carries); `link` is a rendering
 * detail appended to the visible entry only.
 */
export const HOME_FAQ: {
  question: string;
  answer: string;
  link?: { path: string; label: string };
}[] = [
  {
    question: "Est-ce vraiment gratuit et sans engagement ?",
    answer:
      "Oui. Il n'y a ni paiement ni contrat à aucune étape. Répondre aux " +
      "questions ne vous engage à rien et ne déclenche aucune commande.",
  },
  {
    question: "Que deviennent les informations que je transmets ?",
    answer:
      "Elles servent à analyser votre demande et à y répondre. Elles sont " +
      "conservées au maximum 24 mois à compter de votre dernière interaction, " +
      "et vos coordonnées ne sont pas cédées à des partenaires commerciaux " +
      "indépendants à des fins de prospection sans votre information préalable.",
    link: { path: "__privacy__", label: "Politique de confidentialité" },
  },
  {
    question: "Pourquoi n'affichez-vous pas mes économies directement ?",
    answer:
      "Parce qu'une estimation de rentabilité dépend de l'ensoleillement de " +
      "votre adresse, de l'orientation et de l'inclinaison de votre toit, de " +
      "votre profil de consommation et des tarifs en vigueur. Tant que ces " +
      "données ne sont pas intégrées de façon vérifiable, afficher un montant " +
      "serait une invention.",
  },
  // Les deux entrées financement (P1.2). Réponse courte d'abord, forme
  // conditionnelle, jamais la promesse — la politique d'affirmations vaut
  // aussi pour la copie écrite à la main.
  {
    question: "Faut-il disposer d'un apport pour installer des panneaux solaires ?",
    answer:
      "Pas nécessairement. Selon votre situation et le montage de financement " +
      "retenu, le projet peut être réalisé sans mobiliser votre épargne au " +
      "départ — certains frais peuvent rester à votre charge, et ils vous " +
      "sont confirmés avant tout engagement.",
    link: {
      path: "/panneaux-solaires-sans-apport",
      label: "Ce que « sans apport » veut vraiment dire",
    },
  },
  {
    question: "Une installation photovoltaïque peut-elle s'autofinancer ?",
    answer:
      "Elle peut s'en approcher, sans que ce soit garanti : si les économies " +
      "d'électricité mensuelles atteignent la mensualité du financement, " +
      "l'effort net devient faible ou nul. Cela dépend de votre production, " +
      "de votre consommation, du prix de l'électricité et des conditions de " +
      "financement — c'est ce que l'étude personnalisée chiffre.",
  },
  {
    question: "Puis-je revenir sur mon consentement ?",
    answer:
      "Oui, à tout moment. Le consentement au traitement de votre demande et " +
      "celui à recevoir des informations commerciales sont deux cases " +
      "distinctes ; aucune n'est pré-cochée, et refuser la seconde n'empêche " +
      "pas votre demande d'être traitée.",
  },
];

export function Faq({ config, locale }: Ctx) {
  const privacyPath = config?.legal.privacy_policy_path ?? "/confidentialite";
  return (
    <section className="band" aria-labelledby="faq">
      <div className="container container--wide">
        <div className="section-head">
          <p className="eyebrow">Questions fréquentes</p>
          <h2 id="faq">Ce que vous vous demandez sans doute</h2>
        </div>
        <div className="faq">
          {HOME_FAQ.map(({ question, answer, link }) => {
            const target = link?.path === "__privacy__" ? privacyPath : link?.path;
            return (
              <details key={question}>
                <summary>{question}</summary>
                <p>
                  {answer}
                  {target && link &&
                  (target === FINANCING_PATH
                    ? financingLandingVisible(config)
                    : isKnownRoute(config, target)) ? (
                    <>
                      {" "}
                      <Link href={localizedPath(config, locale, target)}>
                        {link.label}
                      </Link>
                    </>
                  ) : null}
                </p>
              </details>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ── Final CTA ──────────────────────────────────────────────────────────── */

/**
 * Strong, and deliberately without an urgency device: no countdown, no scarcity,
 * no "3 places restantes". Manufactured urgency beside sourced figures would
 * undo the figures, which is the reasoning already recorded in
 * `docs/site/CONVERSION_FUNNEL.md`.
 */
export function FinalCta({ config, locale }: Ctx) {
  return (
    <section className="band band--brand final-cta" aria-labelledby="final-cta">
      <div className="container">
        <div className="section-head section-head--center">
          <h2 id="final-cta">Prêt à cadrer votre projet&nbsp;?</h2>
          <p>
            Quelques minutes suffisent. Vous saurez ce que votre toiture permet,
            et nous saurons comment vous répondre utilement.
          </p>
        </div>
        <div className="cta-actions">
          <PrimaryCta config={config} locale={locale} />
        </div>
        <p className="final-cta__note">
          Gratuit, sans engagement, et vous pouvez retirer votre consentement à
          tout moment.
        </p>
      </div>
    </section>
  );
}

export { IconCheck, IconClipboard, IconPerson };
