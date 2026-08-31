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
 * Landing « sans apport » — the transactional page of the financing cluster.
 *
 * Two disciplines govern every sentence here, and they are the page's actual
 * value proposition:
 *
 * 1. NO INVENTED FIGURE. The only numbers this page may show come from the
 *    first-party offer registry, and only once the owner has validated them AND
 *    the legal review is lifted (`offer.publishable`). Until then the page
 *    explains the METHOD — savings minus instalment — and says plainly that the
 *    figures are established during the personalised study. A fake worked
 *    example would convert better and be the exact thing this site exists not
 *    to do.
 *
 * 2. CONDITIONAL, NEVER PROMISSIVE. "Sans apport" is a question the page
 *    answers honestly ("selon votre situation et le montage retenu"), not a
 *    guarantee it makes. The claim-policy gate blocks the promissive form in
 *    generated content; this hand-written page holds itself to the same rule.
 *
 * PUBLICATION GATE (P0.3): while the site is staging, the page is reachable for
 * construction and review. Once the site is public, it serves — and is listed,
 * and is indexable — ONLY when the offer registry is publishable (owner
 * validation AND legal review, independently). A financing page is or leads to
 * consumer-credit advertising, and its mandatory wording is the lawyer's to
 * supply — rendered verbatim from `offer.mandatory_disclosures` when present.
 */

const PATH = "/panneaux-solaires-sans-apport";

const TITLE = "Installer des panneaux solaires sans apport en Belgique";
const DESCRIPTION =
  "Selon votre situation, un projet photovoltaïque peut être financé sans " +
  "mobiliser votre épargne. Ce que « sans apport » veut vraiment dire, quels " +
  "frais peuvent rester, et comment comparer mensualité et économies.";

// ≤ 50 mots, factuelle, conditionnelle — la réponse qu'un moteur de réponse
// peut citer telle quelle. Le compte de mots est épinglé par un test.
const DIRECT_ANSWER =
  "Oui, sous conditions : selon votre profil et le montage de financement " +
  "retenu, une installation photovoltaïque peut être réalisée en Belgique " +
  "sans mobiliser d'épargne au départ. Des frais peuvent rester à votre " +
  "charge ; les conditions exactes sont établies lors de l'étude.";

const FAQ = [
  {
    question: "Faut-il un apport pour installer des panneaux solaires ?",
    answer:
      "Pas nécessairement. Selon votre situation et le montage de financement " +
      "retenu, le projet peut être réalisé sans mobiliser votre épargne au " +
      "départ. Certains frais peuvent rester à votre charge ; ils vous sont " +
      "confirmés avant tout engagement, pendant l'étude.",
  },
  {
    question: "Une installation photovoltaïque peut-elle s'autofinancer ?",
    answer:
      "Elle peut s'en approcher, sans que ce soit garanti : si les économies " +
      "d'électricité mensuelles atteignent ou dépassent la mensualité du " +
      "financement, l'effort net devient faible ou nul. Cela dépend de votre " +
      "production, de votre consommation, du prix de l'électricité et des " +
      "conditions de financement — c'est précisément ce que l'étude chiffre.",
  },
  {
    question: "Quels frais faut-il prévoir au départ ?",
    answer:
      "Cela dépend du montage. Certains montages prévoient des frais de " +
      "dossier ; leur montant exact vous est communiqué lors de l'étude, " +
      "avant tout engagement. Aucun paiement n'est demandé pour l'étude " +
      "elle-même.",
  },
  {
    question: "Comment savoir si mon projet est éligible ?",
    answer:
      "L'éligibilité s'évalue au cas par cas : statut de propriétaire, " +
      "toiture, consommation et situation financière entrent en compte. Le " +
      "questionnaire de demande d'étude rassemble ces éléments et vous " +
      "obtenez une réponse personnalisée, sans engagement.",
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
  const applicationFee = fact(offer, "application_fee_eur");
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
        <p className="eyebrow">Financement photovoltaïque · Belgique</p>
        <h1>{TITLE}</h1>
        <p className="hero__lede">
          Un projet solaire n&apos;exige pas toujours une épargne disponible.
          Selon votre situation, différentes solutions de financement peuvent
          être étudiées — et cette page explique ce que « sans apport » veut
          vraiment dire, sans rien promettre que votre étude ne confirmerait
          pas.
        </p>
        <p>
          <Link className="button button--large" href={formHref} data-cta="primary">
            Vérifier mon projet
          </Link>
        </p>
      </header>

      <DirectAnswer question="Peut-on installer des panneaux solaires sans apport en Belgique ?">
        <p>{DIRECT_ANSWER}</p>
      </DirectAnswer>

      {/* ── 1. Pourquoi l'investissement initial bloque ── */}
      <h2>Pourquoi l&apos;investissement initial bloque certains ménages</h2>
      <p>
        Une installation photovoltaïque résidentielle représente plusieurs
        milliers d&apos;euros. Beaucoup de ménages qui paieraient volontiers
        leur électricité moins cher n&apos;ont pas cette somme disponible — ou
        préfèrent ne pas immobiliser leur épargne. Conclure que le solaire
        « n&apos;est pas pour eux » est souvent prématuré : la vraie question
        n&apos;est pas « ai-je le montant ? » mais « le coût mensuel du
        financement est-il inférieur à ce que je paie déjà pour la même
        électricité ? ».
      </p>

      {/* ── 2. Comment fonctionne un financement photovoltaïque ── */}
      <h2>Comment fonctionne un financement photovoltaïque</h2>
      <p>
        Le principe est celui de tout financement : un organisme avance le coût
        de l&apos;installation, et vous le remboursez par mensualités sur une
        durée convenue. La spécificité du photovoltaïque est que
        l&apos;installation produit dès le premier mois une électricité que
        vous ne payez plus à votre fournisseur : le financement s&apos;évalue
        donc toujours <em>en regard</em> de cette économie, pas dans
        l&apos;absolu.
      </p>
      <p>
        Les conditions précises — organisme, taux, durée — dépendent du montage
        retenu et de votre profil. Elles vous sont présentées noir sur blanc
        lors de l&apos;étude, avant toute décision.
      </p>

      {/* ── 3. Ce que « sans apport » signifie réellement ── */}
      <h2>Ce que « sans apport » signifie réellement</h2>
      <p>
        « Sans apport » signifie une chose précise : le montage ne vous demande
        pas de mobiliser une épargne au départ pour couvrir le prix de
        l&apos;installation. Cela ne signifie pas « sans engagement » — un
        financement reste un contrat — ni « sans aucun frais » : selon le
        montage, certains frais peuvent rester à votre charge. Une offre
        sérieuse vous dit lesquels avant de vous demander quoi que ce soit.
      </p>

      {/* ── 4. Quels frais peuvent rester à payer ── */}
      <h2>Quels frais peuvent rester à payer</h2>
      {applicationFee ? (
        <p>
          Dans le montage proposé, des frais de dossier de{" "}
          <strong>{String(applicationFee.value)}&nbsp;€</strong> sont à
          prévoir. Ils vous sont confirmés par écrit avant tout engagement.
        </p>
      ) : (
        <p>
          Selon le montage, des frais de dossier peuvent être demandés. Leur
          montant exact dépend de l&apos;offre applicable à votre situation et
          vous est communiqué lors de l&apos;étude,{" "}
          <strong>avant tout engagement</strong> — jamais après. La demande
          d&apos;étude elle-même ne donne lieu à aucun paiement.
        </p>
      )}

      {/* ── 5. Mensualité vs économies ── */}
      <h2>Mensualité ou économies : la seule comparaison qui compte</h2>
      <p>
        Le bon critère n&apos;est pas le prix total de l&apos;installation,
        mais l&apos;écart mensuel entre ce que le financement coûte et ce que
        l&apos;installation fait économiser :
      </p>
      <div
        className="method-formula"
        role="img"
        aria-label="Économie mensuelle estimée, moins la mensualité du financement, égale l'impact mensuel net"
      >
        <p>Économie mensuelle estimée</p>
        <p>− mensualité du financement</p>
        <p className="method-formula__result">= impact mensuel net</p>
      </div>
      <p>
        Cette page n&apos;affiche volontairement aucun chiffre pour ces trois
        lignes : votre production dépend de votre toiture, votre économie de
        votre consommation et des tarifs, votre mensualité du montage retenu.
        Un « exemple type » qui ignorerait tout cela serait une invention —
        l&apos;étude personnalisée remplit la formule avec vos données.
      </p>

      {/* ── 6. Conditions d'approche de l'autofinancement ── */}
      <h2>
        Dans quelles conditions une installation peut approcher
        l&apos;autofinancement
      </h2>
      <p>
        Plus l&apos;économie mensuelle se rapproche de la mensualité, plus le
        projet se finance par lui-même. Quatre paramètres font l&apos;essentiel
        de l&apos;écart&nbsp;:
      </p>
      <ul>
        <li>
          <strong>La part d&apos;autoconsommation</strong> — l&apos;électricité
          consommée au moment où elle est produite est celle qui rapporte le
          plus.
        </li>
        <li>
          <strong>Le profil de consommation</strong> — une consommation diurne
          (télétravail, pompe à chaleur, recharge) valorise mieux la
          production.
        </li>
        <li>
          <strong>Le prix de l&apos;électricité</strong> — plus il est élevé,
          plus chaque kilowattheure autoconsommé pèse.
        </li>
        <li>
          <strong>La durée et le taux du financement</strong> — ils fixent la
          mensualité que l&apos;économie doit égaler.
        </li>
      </ul>
      <p>
        Selon la combinaison de ces paramètres, les économies peuvent couvrir
        une partie — parfois l&apos;essentiel — de la mensualité. Aucun de ces
        cas n&apos;est garanti d&apos;avance&nbsp;: c&apos;est un résultat
        d&apos;étude, pas une promesse de page web.
      </p>

      {/* ── 7. Simulation personnalisée ── */}
      <h2>Une simulation personnalisée plutôt qu&apos;un chiffre générique</h2>
      <p>
        L&apos;étude reprend votre toiture (orientation, inclinaison, surface),
        votre consommation annuelle et vos habitudes, puis met en regard la
        production attendue, l&apos;économie estimée et les solutions de
        financement adaptées à votre situation. Vous repartez avec la formule
        ci-dessus remplie — vos chiffres, pas ceux d&apos;une moyenne.
      </p>

      {/* ── 8. Critères d'éligibilité ── */}
      <h2>Les critères d&apos;éligibilité examinés</h2>
      <ul>
        <li>être propriétaire du logement (ou en cours d&apos;acquisition) ;</li>
        <li>une toiture exploitable — orientation, surface, état ;</li>
        <li>une consommation électrique que la production peut réellement compenser ;</li>
        <li>une situation financière compatible avec le montage envisagé.</li>
      </ul>
      <p>
        Chaque critère s&apos;évalue au cas par cas lors de l&apos;étude. Un
        refus est possible — et vous est expliqué.
      </p>

      {/* ── 9. Étapes ── */}
      <h2>Les étapes de votre projet</h2>
      <ol className="landing-steps">
        <li>Vous décrivez votre logement et votre consommation — quelques minutes, sans engagement.</li>
        <li>Nous analysons la faisabilité et préparons une estimation personnalisée.</li>
        <li>Vous recevez production attendue, économies estimées et solutions de financement, par écrit.</li>
        <li>Vous décidez — avec les chiffres, les conditions et les frais éventuels sous les yeux.</li>
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

      {/* ── 10. FAQ ── */}
      <h2 id="faq-financement">Questions fréquentes sur le financement</h2>
      <div className="faq">
        {FAQ.map(({ question, answer }) => (
          <details key={question}>
            <summary>{question}</summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>

      {/* ── 11. CTA final ── */}
      <CtaBlock
        config={config}
        locale={locale}
        heading="Vérifier ce que votre projet donnerait, avec vos chiffres"
        body="Quelques questions sur votre logement et votre consommation suffisent. L'étude est sans engagement, et les conditions de financement applicables à votre situation vous sont présentées avant toute décision."
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
