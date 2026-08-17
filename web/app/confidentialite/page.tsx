import type { Metadata } from "next";

import { getSiteConfig } from "@/lib/api";

export const metadata: Metadata = {
  title: "Protection de vos données personnelles – Solar Belgium",
  robots: { index: false, follow: false },
};

/**
 * Owner-approved text, version `solar-be-consent-v1.0-2026-08-17`.
 *
 * The controller, the contact address and the version are read from the site
 * configuration rather than repeated here: that configuration is the same value
 * recorded against every consent and sent to Prospect 360, so a page that
 * hardcoded them could drift from what a person actually consented to.
 *
 * Only markup and layout are the renderer's business. The legal meaning is the
 * owner's, and changing it means a new version identifier.
 */
export default async function PrivacyPage() {
  const config = await getSiteConfig();
  const controller = config?.legal.data_controller ?? "BEAVER DATA GROUP";
  const contact = config?.legal.privacy_contact_email ?? "";
  const version = config?.legal.consent_version ?? "—";

  return (
    <div className="container page">
      <h1>Protection de vos données personnelles – Solar Belgium</h1>
      <p>
        <small>
          Version&nbsp;: <code>{version}</code>
        </small>
      </p>

      <h2>Responsable du traitement</h2>
      <p>
        Les données personnelles collectées par l&apos;intermédiaire du site Solar
        Belgium sont traitées sous la responsabilité de&nbsp;:
      </p>
      <address>
        {controller}
        <br />
        SAS – Société par actions simplifiée
        <br />
        43 rue de Marquillies
        <br />
        59000 Lille – France
        <br />
        SIREN&nbsp;: 935 097 675
      </address>
      <p>
        {controller} détermine les finalités et les moyens des traitements
        réalisés dans le cadre du service Solar Belgium.
      </p>

      <h2>Pourquoi collectons-nous vos données&nbsp;?</h2>
      <p>
        Les informations que vous nous transmettez sont utilisées exclusivement
        afin de&nbsp;:
      </p>
      <ul>
        <li>recevoir et enregistrer votre demande concernant un projet solaire&nbsp;;</li>
        <li>analyser les caractéristiques de votre projet&nbsp;;</li>
        <li>évaluer et qualifier votre besoin&nbsp;;</li>
        <li>vous recontacter afin de répondre à votre demande&nbsp;;</li>
        <li>assurer le suivi de votre demande&nbsp;;</li>
        <li>
          assurer la sécurité, la traçabilité et le bon fonctionnement du service.
        </li>
      </ul>
      <p>
        Vos données ne sont pas utilisées à des fins de prospection commerciale
        électronique indépendante de votre demande sans consentement spécifique
        lorsque celui-ci est requis.
      </p>

      <h2>Quelles données peuvent être collectées&nbsp;?</h2>
      <p>
        Selon les informations que vous renseignez dans le formulaire, nous pouvons
        notamment traiter&nbsp;:
      </p>
      <ul>
        <li>vos nom et prénom&nbsp;;</li>
        <li>votre adresse électronique&nbsp;;</li>
        <li>votre numéro de téléphone&nbsp;;</li>
        <li>votre code postal&nbsp;;</li>
        <li>votre situation par rapport au logement&nbsp;;</li>
        <li>le type de bien concerné&nbsp;;</li>
        <li>le calendrier envisagé pour votre projet&nbsp;;</li>
        <li>les caractéristiques de votre toiture&nbsp;;</li>
        <li>son orientation&nbsp;;</li>
        <li>votre consommation annuelle d&apos;énergie&nbsp;;</li>
        <li>
          les informations techniques nécessaires au suivi et à la traçabilité de
          votre demande.
        </li>
      </ul>
      <p>
        Seules les informations nécessaires à l&apos;étude et au suivi de votre
        projet sont collectées.
      </p>

      <h2>Base juridique du traitement</h2>
      <p>
        Lorsque vous validez le formulaire, vous consentez au traitement des données
        que vous avez communiquées pour la gestion et le suivi de votre demande Solar
        Belgium.
      </p>
      <p>
        Votre consentement peut être retiré à tout moment. Le retrait du consentement
        n&apos;affecte pas la licéité des traitements effectués avant ce retrait.
      </p>

      <h2>Destinataires des données</h2>
      <p>Les données sont accessibles uniquement&nbsp;:</p>
      <ul>
        <li>
          aux personnes habilitées de {controller} ayant besoin d&apos;y accéder
          pour traiter votre demande&nbsp;;
        </li>
        <li>
          aux prestataires techniques agissant pour le compte de {controller} et
          strictement nécessaires au fonctionnement, à l&apos;hébergement, à la
          sécurité ou au traitement du service.
        </li>
      </ul>
      <p>
        Vos coordonnées ne sont pas transmises à des partenaires commerciaux
        indépendants à des fins de prospection sans information préalable et,
        lorsque la réglementation l&apos;exige, sans votre consentement spécifique.
      </p>

      <h2>Durée de conservation</h2>
      <p>
        Les données relatives à votre demande sont conservées pendant une durée
        maximale de 24&nbsp;mois (730&nbsp;jours) à compter de leur collecte ou de
        votre dernière interaction avec Solar Belgium, sauf si&nbsp;:
      </p>
      <ul>
        <li>vous demandez leur suppression auparavant&nbsp;;</li>
        <li>une obligation légale impose une conservation différente&nbsp;;</li>
        <li>
          leur conservation est nécessaire à la constatation, à l&apos;exercice ou à
          la défense d&apos;un droit en justice.
        </li>
      </ul>

      <h2>Vos droits</h2>
      <p>
        Conformément à la réglementation applicable en matière de protection des
        données, vous disposez, selon les conditions prévues par celle-ci, notamment
        des droits suivants&nbsp;:
      </p>
      <ul>
        <li>droit d&apos;accès&nbsp;;</li>
        <li>droit de rectification&nbsp;;</li>
        <li>droit à l&apos;effacement&nbsp;;</li>
        <li>droit à la limitation du traitement&nbsp;;</li>
        <li>droit à la portabilité lorsque celui-ci est applicable&nbsp;;</li>
        <li>droit de retirer votre consentement à tout moment&nbsp;;</li>
        <li>
          droit de vous opposer à certains traitements lorsque ce droit est
          applicable.
        </li>
      </ul>
      <p>Pour exercer vos droits&nbsp;:</p>
      <p>
        Email&nbsp;: <a href={`mailto:${contact}`}>{contact}</a>
      </p>
      <p>Courrier&nbsp;:</p>
      <address>
        {controller}
        <br />
        43 rue de Marquillies
        <br />
        59000 Lille
        <br />
        France
      </address>
      <p>
        Une vérification d&apos;identité pourra être demandée lorsque cela est
        nécessaire pour éviter qu&apos;un tiers accède aux données d&apos;une autre
        personne.
      </p>
      <p>
        Vous pouvez également introduire une réclamation auprès de l&apos;autorité de
        contrôle compétente en matière de protection des données.
      </p>

      <h2>Sécurité</h2>
      <p>
        {controller} met en œuvre des mesures techniques et organisationnelles
        destinées à protéger vos données contre l&apos;accès non autorisé, la perte,
        l&apos;altération ou la divulgation illicite.
      </p>
      <p>
        Les accès aux données sont limités aux personnes et systèmes qui en ont
        besoin dans le cadre des finalités décrites ci-dessus.
      </p>

      <h2>Modification de la politique</h2>
      <p>
        La présente politique peut être mise à jour en fonction des évolutions du
        service ou de la réglementation.
      </p>
      <p>
        La version applicable au moment de votre consentement est enregistrée afin
        de permettre la traçabilité de celui-ci.
      </p>
    </div>
  );
}
