# SOLAR_BE — Pack de revue juridique : le modèle SG Solution

**Statut : EN ATTENTE DE REVUE. Ce document ne contient aucune conclusion
juridique.** Version 2 (2026-08-31) : la version 1 raisonnait sur une
hypothèse de crédit/financement qui n'était pas le modèle. Le juriste examine
maintenant le modèle réel, owner-supplied le 2026-08-31, dont la
**qualification juridique est inconnue** — le site ne le décrit nulle part
comme un crédit, un PPA, un leasing, une location-vente ou une fourniture
d'énergie (« solution SG Solution », provisoirement).

Tant que cette revue n'a pas eu lieu, `offer.pending_legal_review: true`
maintient la landing non-publiable et hors sitemap, et `usable_facts` reste
vide : AUCUN des chiffres ci-dessous n'est servi publiquement.

## 0. Les entités

| Entité | Rôle | Identité |
|---|---|---|
| Mon Projet Solaire | marque, site, parcours d'acquisition | pas une entité juridique |
| Beaver Data Group | opérateur : acquisition, qualification, consentement, rendez-vous, transmission | SIREN 935097675, 43 rue de Marquillies, 59000 Lille (FR) |
| SG Solution | fournisseur de la solution : analyse, décision d'éligibilité, contrat, livraison | **identité légale NON FOURNIE** (blocker, voir Owner Pack) |

## 1. Le modèle owner-supplied (registre `sg-solution-solar-25y-v0.1-draft`)

Chaque fait est au registre avec provenance first-party et date de fourniture
2026-08-31 ; `evidence.contract_reference: null` — aucune preuve
contractuelle n'a été remise.

| Fait | Valeur fournie |
|---|---|
| Installation mise à disposition | panneaux solaires + batterie domestique |
| Durée du contrat | 25 ans |
| Tarif de l'électricité produite | 0,27 €/kWh |
| Tarif annoncé | fixe sur la durée |
| Frais administratifs | 150 €, une fois, à la signature |
| Crédit bancaire classique | non requis |
| Rachat en cours de contrat | possible |
| Réduction annuelle annoncée du prix de rachat | 4 % (référence : valeur initiale de l'installation ; assiette, méthode, plancher, HT/TTC non définis) |
| Au terme (25 ans) | transfert automatique de propriété (panneaux + batterie) |
| Si installation techniquement impossible | offre énergétique alternative SG Solution possible — AUCUN tarif fourni |
| Éligibilité (exclusions) | tarif social de l'énergie : non éligible ; amiante en toiture : non admise ; installation électrique conforme et en bon état requise ; faisabilité du bâtiment ; décision finale : SG Solution après analyse |
| Ciblage owner-supplied | personnes souhaitant panneaux + batterie, y compris en cas de difficulté d'accès au crédit bancaire ou de budget insuffisant pour un achat immédiat |

## 2. Formulations exactes actuellement servies (verbatim)

Le juriste juge CES textes. Sources :
`web/app/panneaux-solaires-sans-apport/page.tsx` (landing),
`web/components/home/Sections.tsx` (accueil),
`config/sites/solar_be.yaml` (métas, consentements).
Les chiffres du registre ne sont PAS dans ces textes aujourd'hui — chaque
bloc chiffré a un état générique servi tant que l'offre n'est pas publiable ;
l'état chiffré (entre ⟨⟩ ci-dessous) est celui qui serait servi après levée
des verrous.

**Méta / balisage :**

- **L-1** (title/H1) : « Installer des panneaux solaires sans apport en
  Belgique »
- **L-2** (meta description) : « Selon votre situation, une installation
  solaire avec batterie peut être mise à disposition sans acheter l'ensemble
  immédiatement. Ce que la solution recouvre, les conditions examinées, et
  comment se décide l'éligibilité. »
- **L-3** (réponse directe, aussi en JSON-LD) : « Oui, sous conditions : une
  installation solaire avec batterie domestique peut être mise à disposition
  dans le cadre d'un contrat de longue durée, sans acheter l'ensemble
  immédiatement. L'éligibilité est décidée après analyse de votre dossier ;
  les conditions exactes vous sont présentées avant tout engagement. »

**Corps de la landing :**

- **L-4** (hero) : « Un projet solaire n'exige pas toujours d'acheter
  l'installation d'un coup. Selon votre situation, une installation avec
  batterie peut être mise à disposition dans le cadre d'un contrat — et cette
  page explique ce que cela recouvre, sans rien promettre que l'analyse de
  votre dossier ne confirmerait pas. »
- **L-5** (public visé) : « Aux ménages propriétaires qui veulent produire
  leur électricité — panneaux et batterie domestique — sans immobiliser d'un
  coup le montant d'une installation complète. Cela inclut les situations où
  un achat immédiat n'est pas envisageable ou pas souhaité, quelle qu'en soit
  la raison […] »
- **L-6** (fonctionnement, état générique servi) : « l'installation —
  panneaux solaires et batterie — est mise à votre disposition dans le cadre
  d'un contrat de longue durée. Vous utilisez l'électricité produite chez
  vous, à un tarif défini au contrat et communiqué lors de l'étude. Selon le
  contrat, des frais uniques peuvent être dus à la signature ; leur montant
  exact vous est communiqué lors de l'étude, avant tout engagement. »
  ⟨état chiffré : « contrat de longue durée de 25 ans », « à un tarif défini
  au contrat de 0,27 €/kWh », « Des frais administratifs uniques de 150 €
  sont dus à la signature »⟩
- **L-7** (nature du contrat) : « La nature juridique précise du contrat,
  ses conditions et ses mentions vous sont présentées noir sur blanc dans la
  proposition écrite — c'est sur pièces que l'on s'engage, pas sur une page
  web. »
- **L-8** (propriété) : « Selon les termes du contrat proposé, deux chemins
  peuvent exister : le rachat de l'installation en cours de contrat ⟨à un
  prix qui, selon les termes annoncés, diminue de 4 % par an par rapport à la
  valeur initiale de l'installation⟩ et le transfert de propriété au terme
  ⟨des 25 ans⟩. L'assiette exacte, la méthode de calcul et les conditions de
  chacun figurent dans le contrat — cette page n'en calcule aucune
  projection […] »
- **L-9** (conditions examinées) : liste — propriétaire ; « ne pas
  bénéficier du tarif social de l'énergie » ; « une toiture sans amiante,
  techniquement adaptée » ; « une installation électrique conforme et en bon
  état » ; logement compatible. Puis : « La décision finale appartient à
  SG Solution, après analyse du dossier et vérification technique — un refus
  est possible, et il vous est expliqué. »
- **L-10** (alternative) : « Dans ce cas, SG Solution peut proposer une
  solution énergétique alternative. Ses conditions et son tarif dépendent de
  votre situation et vous sont présentés lors de l'analyse — cette page
  n'avance aucun chiffre à leur sujet. »
- **L-11** (qui fait quoi) : les trois rôles, dont « [Beaver Data Group]
  n'installe pas, ne fournit pas d'électricité et ne décide pas de
  l'éligibilité. »

**FAQ landing :**

- **L-12** : « Pas nécessairement. Selon votre situation et la solution
  retenue, l'installation peut être mise à disposition sans acheter
  l'ensemble immédiatement. Certains frais peuvent rester à votre charge ;
  ils vous sont confirmés avant tout engagement, pendant l'étude. »
- **L-13** (crédit bancaire) : « Selon la solution retenue, le passage par
  un crédit bancaire classique peut ne pas être requis — c'est l'un des
  points que l'analyse de votre dossier précise. La nature exacte du contrat
  et ses conditions vous sont présentées par écrit avant toute décision. »
- **L-14** (acceptation) : « Non — et méfiez-vous de quiconque vous le
  promet. Le questionnaire permet une première vérification des critères ;
  la décision d'éligibilité appartient à SG Solution, après analyse de votre
  dossier et vérification technique. Un refus est possible et vous est
  expliqué. »
- **L-15** (terme du contrat) : « Selon les termes du contrat proposé,
  l'installation peut être rachetée en cours de contrat ou devenir votre
  propriété au terme. Les modalités exactes — durée, conditions de rachat,
  transfert — figurent dans la proposition écrite qui vous est remise avant
  tout engagement. »

**Accueil :**

- **L-16** (hero) : « Pas d'épargne à mobiliser ? Selon votre situation, une
  installation avec batterie peut être mise à disposition sans achat
  immédiat. »
- **L-17** (FAQ apport) : comme L-12, forme courte.
- **L-18** (FAQ autofinancement) : « Elle peut s'en approcher, sans que ce
  soit garanti : si les économies d'électricité mensuelles atteignent le coût
  mensuel de la solution retenue, l'effort net devient faible ou nul. […] »
- **L-19** (méta description par défaut du site) : « […] Selon votre
  situation, une installation avec batterie peut être mise à disposition
  sans achat immédiat. »

**Consentements (versionnés, servis au formulaire) :**

- **L-20** (transmission partenaire, v1.0-2026-08-30) : « J'accepte que mes
  coordonnées et les caractéristiques de mon projet soient transmises à
  Solution SG, partenaire installateur de BEAVER DATA GROUP, dans le seul
  but d'organiser un rendez-vous relatif à mon projet solaire. BEAVER DATA
  GROUP demeure responsable de ce traitement. Je peux retirer ce
  consentement à tout moment. » — ATTENTION : dit « Solution SG, partenaire
  installateur » et « dans le seul but d'organiser un rendez-vous » ; le rôle
  réel (analyse du dossier, décision, proposition contractuelle) est plus
  large, et la qualité d'« installateur » n'est pas établie. Texte à
  revalider ; toute modification = nouvelle version de consentement.

## 3. Questions au juriste (réponses écrites attendues)

Qualification du contrat :
1. Quelle est la qualification juridique exacte du contrat SG Solution ?
2. Relève-t-il d'un crédit à la consommation ? 3. D'un PPA ? 4. D'une
location ? 5. D'un leasing ? 6. D'une location-vente ? 7. D'une fourniture
d'énergie ? 8. D'un autre mécanisme (lequel) ?

Rôle et communication de l'opérateur :
9. Beaver Data Group peut-il légalement présenter et promouvoir cette offre
(statut d'intermédiaire ? agrément ?) ?
10. « Sans apport » (L-1) est-il utilisable pour ce modèle ?
11. « Aucun crédit bancaire classique nécessaire » est-il utilisable, et sous
quelle forme (l'actuelle L-13 est conditionnelle) ?
12. Peut-on communiquer explicitement vers les personnes refusées par les
banques ? (Aujourd'hui le site ne le fait PAS — L-5 décrit le public par son
projet.)

Le tarif :
13. Comment 0,27 €/kWh doit-il être présenté ? 14. Peut-il être qualifié de
« fixe » ? 15. De « garanti pendant 25 ans » ? 16. Quelles mentions doivent
accompagner cette affirmation, mot pour mot ?

Les frais et le rachat :
17. Comment présenter les 150 € (dénomination, moment, caractère unique) ?
18. Comment présenter l'option de rachat ? 19. La « réduction annuelle de
4 % » est-elle présentable, et avec quelle définition d'assiette ? 20. Quelle
est exactement la formule contractuelle de rachat (à exiger de SG Solution) ?
21. Comment présenter le transfert final de propriété ?

L'offre alternative :
22. SG Solution dispose-t-elle des autorisations nécessaires pour proposer
l'offre alternative d'électricité (statut de fournisseur ?) ?
23. « Tarif avantageux » est-il utilisable sans comparatif sourcé ?
24. « Tarif compétitif » ?

RGPD :
25. Quelles obligations s'appliquent à la transmission du lead à SG
Solution ? 26. Quel est le rôle RGPD de Beaver Data Group ? 27. Celui de SG
Solution (responsables indépendants ? conjoints ? sous-traitant ?) — le code
ne le décide pas. 28. Le consentement marketing doit-il rester séparé de la
transmission nécessaire au traitement (aujourd'hui : oui, quatre cases
distinctes) ? 29. Quelles mentions pour la prise de rendez-vous ?
30. Quelles informations doivent apparaître avant le CTA / le formulaire ?
31. Le texte L-20 (transmission « Solution SG, partenaire installateur »,
finalité « organiser un rendez-vous ») couvre-t-il le flux réel
(analyse du dossier + décision + proposition) ? Sinon, fournir le texte —
nouvelle version de consentement.
32. La destination de notification des leads (boîte Gmail de l'opérateur)
appelle-t-elle des mesures particulières (transfert hors UE, DPA) ?

## 4. Matrice de verdicts — à remplir par le réviseur

APPROVED (tel quel) / CONDITIONAL (reformulation et/ou mention exigées,
verbatim) / FORBIDDEN (à retirer). CONDITIONAL sans reformulation écrite
compte comme FORBIDDEN.

| ID | Verdict | Reformulation exigée (verbatim) | Mention obligatoire associée | Base légale invoquée | Date | Réviseur |
|---|---|---|---|---|---|---|
| L-1 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-2 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-3 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-4 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-5 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-6 (générique ET chiffré) | ______ | ______ | ______ | ______ | ______ | ______ |
| L-7 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-8 (générique ET chiffré) | ______ | ______ | ______ | ______ | ______ | ______ |
| L-9 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-10 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-11 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-12 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-13 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-14 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-15 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-16 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-17 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-18 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-19 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-20 | ______ | ______ | ______ | ______ | ______ | ______ |

## 5. Ce que la revue déclenche techniquement

1. Reformulations CONDITIONAL appliquées, FORBIDDEN retirés ; L-20 modifié
   = NOUVELLE version de consentement (le registre de consentement est
   versionné, l'ancien texte reste attaché aux leads qui l'ont vu).
2. `offer.legal.mandatory_disclosures` reçoit les mentions verbatim — la
   landing les rend telles quelles.
3. `offer.legal.reviewed_at` + `reviewer` ; `pending_legal_review: false`.
4. La publiabilité exige EN PLUS `status: validated` + `owner_validated_at`
   (les deux verrous sont indépendants) — et les faits « fixe/garanti »
   attendent aussi `evidence.contract_reference` (le contrat type de SG
   Solution, à exiger — voir Owner Pack §2).

Aucun de ces champs n'est rempli par le développeur de sa propre initiative.
