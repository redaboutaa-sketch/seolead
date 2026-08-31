import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CtaBlock } from "@/components/Cta";
import { DirectAnswer } from "@/components/DirectAnswer";
import { getSiteConfig } from "@/lib/api";
import { faqNode, graph, serviceNode, webPageNode, websiteNode } from "@/lib/jsonld";
import { pageMetadata } from "@/lib/metadata";
import { financingLandingVisible, localizedPath } from "@/lib/site";
import type { OfferDTO, SiteConfigDTO } from "@/lib/types";

/**
 * Landing « sans apport » — aligned with the REAL model (2026-08-31).
 *
 * The model this page describes is the SG Solution offer: an installation
 * (solar panels + home battery) made available under a long-term contract,
 * with a possible buyout and an ownership transfer at term. Its legal nature
 * is deliberately UNQUALIFIED — not called a credit, a lease, a PPA or an
 * energy-supply contract anywhere, because that qualification is the
 * lawyer's, not this file's. Provisional naming: « solution SG Solution ».
 *
 * Three disciplines govern every sentence:
 *
 * 1. NO FIGURE OUTSIDE THE REGISTRY. Duration, tariff, fee, buyout and term
 *    render ONLY from `offer.facts` — which the API serves only when the
 *    offer is publishable (owner validation AND legal review). Until then
 *    every block falls back to « présenté lors de l'étude ».
 *
 * 2. CONDITIONAL, NEVER PROMISSIVE. Prequalification is the operator's;
 *    the DECISION is SG Solution's, after analysis — the page says so
 *    instead of promising acceptance, and the claim-policy gates
 *    (UNCONDITIONAL_CONTRACT_PROMISE, UNCONDITIONAL_ACCEPTANCE_PROMISE)
 *    hold generated content to the same rule.
 *
 * 3. ENTITIES NEVER BLURRED. Mon Projet Solaire is the brand and the
 *    acquisition journey; Beaver Data Group operates it (qualification,
 *    consent, appointment, transmission); SG Solution analyses, decides and
 *    contracts. The « qui fait quoi » section states it in that order.
 *
 * PUBLICATION GATE unchanged: reachable in staging for construction and
 * review; on the public site it serves, is listed and is indexable ONLY when
 * `offer.publishable` — and the lawyer's mandatory wording renders verbatim
 * from `offer.mandatory_disclosures` when present.
 */

const PATH = "/panneaux-solaires-sans-apport";

const TITLE = "Installer des panneaux solaires sans apport en Belgique";
const DESCRIPTION =
  "Selon votre situation, une installation solaire avec batterie peut être " +
  "mise à disposition sans acheter l'ensemble immédiatement. Ce que la " +
  "solution recouvre, les conditions examinées, et comment se décide " +
  "l'éligibilité.";

// ≤ 50 mots, factuelle, conditionnelle — la réponse qu'un moteur de réponse
// peut citer telle quelle. Le compte de mots est épinglé par un test.
const DIRECT_ANSWER =
  "Oui, sous conditions : une installation solaire avec batterie domestique " +
  "peut être mise à disposition dans le cadre d'un contrat de longue durée, " +
  "sans acheter l'ensemble immédiatement. L'éligibilité est décidée après " +
  "analyse de votre dossier ; les conditions exactes vous sont présentées " +
  "avant tout engagement.";

const FAQ = [
  {
    question: "Faut-il un apport pour installer des panneaux solaires ?",
    answer:
      "Pas nécessairement. Selon votre situation et la solution retenue, " +
      "l'installation peut être mise à disposition sans acheter l'ensemble " +
      "immédiatement. Certains frais peuvent rester à votre charge ; ils " +
      "vous sont confirmés avant tout engagement, pendant l'étude.",
  },
  {
    question: "Dois-je obtenir un crédit auprès de ma banque ?",
    answer:
      "Selon la solution retenue, le passage par un crédit bancaire " +
      "classique peut ne pas être requis — c'est l'un des points que " +
      "l'analyse de votre dossier précise. La nature exacte du contrat et " +
      "ses conditions vous sont présentées par écrit avant toute décision.",
  },
  {
    question: "Suis-je certain d'être accepté ?",
    answer:
      "Non — et méfiez-vous de quiconque vous le promet. Le questionnaire " +
      "permet une première vérification des critères ; la décision " +
      "d'éligibilité appartient à SG Solution, après analyse de votre " +
      "dossier et vérification technique. Un refus est possible et vous " +
      "est expliqué.",
  },
  {
    question: "Que se passe-t-il au terme du contrat ?",
    answer:
      "Selon les termes du contrat proposé, l'installation peut être " +
      "rachetée en cours de contrat ou devenir votre propriété au terme. " +
      "Les modalités exactes — durée, conditions de rachat, transfert — " +
      "figurent dans la proposition écrite qui vous est remise avant tout " +
      "engagement.",
  },
];

export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  return pageMetadata({
    config,
    title: TITLE,
    description: DESCRIPTION,
    path: PATH,
    // Indexable only once the offer registry cleared both locks — even if the
    // site itself is already indexable.
    noindex: !config?.offer?.publishable,
  });
}

// The one gate, shared with everything that links here (hero, FAQ): a page
// that 404s must not be linked, and a page that is linked must be served.
const visible = financingLandingVisible;

/** The validated fact, or null — never a placeholder number. */
function fact(offer: OfferDTO | undefined, id: string) {
  return offer?.facts.find((f) => f.id === id) ?? null;
}

export default async function NoDepositLandingPage() {
  const config = await getSiteConfig();
  if (!visible(config)) notFound();

  const locale = config?.default_language ?? "fr";
  const offer = config?.offer;
  const duration = fact(offer, "contract_duration_years");
  const tariff = fact(offer, "energy_tariff_eur_per_kwh");
  const fee = fact(offer, "administrative_fee_eur");
  const buyoutReduction = fact(offer, "buyout_annual_reduction_percent");
  const ownershipYears = fact(offer, "ownership_transfer_after_years");
  const formHref = localizedPath(config, locale, "/demande-etude");

  const jsonLd = graph(
    websiteNode(config),
    webPageNode(config, PATH, TITLE, DESCRIPTION),
    serviceNode(config, PATH),
    faqNode(config, PATH, FAQ),
  );

  return (
    <article className="container page">
      {/* ── Hero ── */}
      <header>
        <p className="eyebrow">Solutions solaires · Belgique</p>
        <h1>{TITLE}</h1>
        <p className="hero__lede">
          Un projet solaire n&apos;exige pas toujours d&apos;acheter
          l&apos;installation d&apos;un coup. Selon votre situation, une
          installation avec batterie peut être mise à disposition dans le
          cadre d&apos;un contrat — et cette page explique ce que cela
          recouvre, sans rien promettre que l&apos;analyse de votre dossier
          ne confirmerait pas.
        </p>
        <p>
          <Link className="button button--large" href={formHref} data-cta="primary">
            Vérifier mon projet
          </Link>
        </p>
      </header>

      <DirectAnswer question="Peut-on accéder à des panneaux solaires et une batterie sans acheter immédiatement toute l'installation ?">
        <p>{DIRECT_ANSWER}</p>
      </DirectAnswer>

      {/* ── 1. À qui s'adresse la solution ── */}
      <h2>À qui s&apos;adresse cette solution</h2>
      <p>
        Aux ménages propriétaires qui veulent produire leur électricité —
        panneaux et batterie domestique — sans immobiliser d&apos;un coup le
        montant d&apos;une installation complète. Cela inclut les situations
        où un achat immédiat n&apos;est pas envisageable ou pas souhaité,
        quelle qu&apos;en soit la raison : la solution repose sur un contrat
        de mise à disposition, et l&apos;analyse du dossier porte sur votre
        projet et votre logement.
      </p>

      {/* ── 2. Comment fonctionne la solution ── */}
      <h2>Comment fonctionne la solution SG Solution</h2>
      <p>
        Le principe : l&apos;installation — panneaux solaires et batterie —
        est mise à votre disposition dans le cadre d&apos;un contrat de
        longue durée{duration ? (
          <>
            {" "}de <strong>{String(duration.value)}&nbsp;ans</strong>
          </>
        ) : null}. Vous utilisez l&apos;électricité produite chez vous
        {tariff ? (
          <>
            , à un tarif défini au contrat de{" "}
            <strong>{String(tariff.value).replace(".", ",")}&nbsp;€/kWh</strong>
          </>
        ) : (
          <>
            , à un tarif défini au contrat et communiqué lors de l&apos;étude
          </>
        )}.{" "}
        {fee ? (
          <>
            Des frais administratifs uniques de{" "}
            <strong>{String(fee.value)}&nbsp;€</strong> sont dus à la
            signature — ils vous sont confirmés par écrit avant tout
            engagement.
          </>
        ) : (
          <>
            Selon le contrat, des frais uniques peuvent être dus à la
            signature ; leur montant exact vous est communiqué lors de
            l&apos;étude, <strong>avant tout engagement</strong>. La demande
            d&apos;étude elle-même ne donne lieu à aucun paiement.
          </>
        )}
      </p>
      <p>
        La nature juridique précise du contrat, ses conditions et ses
        mentions vous sont présentées noir sur blanc dans la proposition
        écrite — c&apos;est sur pièces que l&apos;on s&apos;engage, pas sur
        une page web.
      </p>

      {/* ── 3. Peut-on devenir propriétaire ── */}
      <h2>Peut-on devenir propriétaire de l&apos;installation&nbsp;?</h2>
      <p>
        Selon les termes du contrat proposé, deux chemins peuvent exister :
        le rachat de l&apos;installation en cours de contrat
        {buyoutReduction ? (
          <>
            {" "}— à un prix qui, selon les termes annoncés, diminue de{" "}
            <strong>{String(buyoutReduction.value)}&nbsp;%</strong> par an
            par rapport à la valeur initiale de l&apos;installation —
          </>
        ) : null}{" "}
        et le transfert de propriété au terme
        {ownershipYears ? (
          <>
            {" "}des <strong>{String(ownershipYears.value)}&nbsp;ans</strong>
          </>
        ) : null}
        . L&apos;assiette exacte, la méthode de calcul et les conditions de
        chacun figurent dans le contrat — cette page n&apos;en calcule
        aucune projection, parce qu&apos;une projection sans la formule
        contractuelle serait une invention.
      </p>

      {/* ── 4. Conditions principales ── */}
      <h2>Les conditions examinées</h2>
      <p>
        L&apos;analyse du dossier vérifie notamment les points suivants —
        les connaître avant d&apos;entamer la démarche évite les mauvaises
        surprises :
      </p>
      <ul>
        <li>être propriétaire du logement (ou en cours d&apos;acquisition) ;</li>
        <li>ne pas bénéficier du tarif social de l&apos;énergie ;</li>
        <li>une toiture sans amiante, techniquement adaptée — orientation, surface, état ;</li>
        <li>une installation électrique conforme et en bon état ;</li>
        <li>un logement compatible avec l&apos;installation envisagée.</li>
      </ul>
      <p>
        Le questionnaire fait une première vérification de ces critères.{" "}
        <strong>La décision finale appartient à SG Solution</strong>, après
        analyse du dossier et vérification technique — un refus est possible,
        et il vous est expliqué.
      </p>

      {/* ── 5. Si l'installation est impossible ── */}
      <h2>Et si votre logement ne convient pas&nbsp;?</h2>
      <p>
        Certaines toitures ou configurations ne permettent pas
        d&apos;installer des panneaux — orientation insuffisante, structure
        incompatible, contraintes techniques. Dans ce cas, SG Solution peut
        proposer une solution énergétique alternative. Ses conditions et son
        tarif dépendent de votre situation et vous sont présentés lors de
        l&apos;analyse — cette page n&apos;avance aucun chiffre à leur
        sujet.
      </p>

      {/* ── 6. Qui fait quoi ── */}
      <h2>Qui fait quoi</h2>
      <ul>
        <li>
          <strong>Mon Projet Solaire</strong> — le site et le parcours de
          demande : décrire votre projet et cadrer votre demande d&apos;étude.
        </li>
        <li>
          <strong>Beaver Data Group</strong> — l&apos;entreprise qui exploite
          ce site : elle recueille votre demande et vos consentements,
          vérifie les premiers critères, organise le rendez-vous éventuel et
          transmet votre dossier. Elle n&apos;installe pas, ne fournit pas
          d&apos;électricité et ne décide pas de l&apos;éligibilité.
        </li>
        <li>
          <strong>SG Solution</strong> — l&apos;entreprise qui propose la
          solution : elle analyse votre dossier, vérifie la faisabilité
          technique, décide de l&apos;éligibilité et, le cas échéant, vous
          adresse une proposition contractuelle.
        </li>
      </ul>

      {/* ── 7. Étapes ── */}
      <h2>Les étapes de votre demande</h2>
      <ol className="landing-steps">
        <li>Vous décrivez votre logement et votre projet sur ce site — quelques minutes, sans engagement.</li>
        <li>Beaver Data Group vérifie les premiers critères et recueille vos consentements.</li>
        <li>Si vous le souhaitez, un rendez-vous est organisé.</li>
        <li>Votre dossier est transmis à SG Solution — avec votre accord explicite, jamais sans.</li>
        <li>SG Solution analyse le dossier et vérifie la faisabilité technique.</li>
        <li>Si votre dossier est retenu, SG Solution vous adresse une proposition écrite — conditions, frais et mentions inclus.</li>
        <li>Vous décidez, avec les pièces sous les yeux. La contractualisation éventuelle se fait avec SG Solution.</li>
      </ol>

      {/* ── Mentions légales du montage (juriste) ── */}
      {offer?.mandatory_disclosures?.length ? (
        <section aria-label="Mentions légales">
          {offer.mandatory_disclosures.map((disclosure) => (
            <p key={disclosure} className="notice">
              {disclosure}
            </p>
          ))}
        </section>
      ) : null}

      {/* ── 8. FAQ ── */}
      <h2 id="faq-financement">Questions fréquentes</h2>
      <div className="faq">
        {FAQ.map(({ question, answer }) => (
          <details key={question}>
            <summary>{question}</summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>

      {/* ── 9. CTA final ── */}
      <CtaBlock
        config={config}
        locale={locale}
        heading="Vérifier si votre projet correspond aux premiers critères"
        body="Quelques questions sur votre logement et votre projet suffisent. La demande est sans engagement, et les conditions applicables à votre situation vous sont présentées par écrit avant toute décision."
      />

      {jsonLd ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd }}
        />
      ) : null}
    </article>
  );
}
