# Audit SEO / AEO / GEO — monprojetsolaire.be

**Date** : 2026-08-31 · **Périmètre** : positionnement « financement / sans apport », moteurs classiques, moteurs de réponse et LLM, accessibilité aux agents, esquisse MCP.
**Document seul. Aucun code n'a été modifié.**

## 0. Ce qui a été audité, et depuis où

Cet audit est fait **depuis le dépôt**, qui est le site : routes Next, métadonnées,
robots, sitemap, JSON-LD, configuration `config/sites/solar_be.yaml`, et la
politique d'affirmations qui décide de ce que le site a le droit de dire.
L'environnement d'audit n'a pas d'accès réseau sortant : rien n'a été « crawlé »
en ligne, et rien n'avait besoin de l'être — le rendu est celui du code, et le
code est là.

Deux faits de cadre commandent tout le reste, et un audit qui ne les met pas en
premier serait malhonnête :

1. **Le site est volontairement invisible.** `allow_indexing: false`,
   `staging: true`, `robots.txt` en `disallow: /`, `noindex,nofollow` sur chaque
   page, sitemap vide tant que non indexable, bandeau de préproduction.
   Tout ceci est fail-closed, correct, et **décision propriétaire**. Conséquence :
   l'action SEO au plus fort impact disponible n'est pas dans cette liste — c'est
   la bascule publique, et elle n'appartient qu'au propriétaire. Tout ce qui suit
   est du travail « prêt à basculer ».
2. **Le site a une discipline de preuve que le nouveau positionnement va
   éprouver.** Chaque affirmation publiée passe par une politique de risque
   (catégorie → risque → autorité → corroboration). Le positionnement
   « sans apport / autofinancé / 150 € de frais de dossier » est constitué
   d'affirmations commerciales de première partie — et la mesure ci-dessous
   montre que la politique actuelle **ne les voit pas**.

## 1. État des lieux

### Ce qui est déjà bon (et rare)

| élément | état |
|---|---|
| `robots.txt` / meta robots | fail-closed, trois conditions indépendantes, calculées par l'API |
| canonicals | résolus contre `canonical_origin` configuré, jamais contre l'hôte de la requête |
| SSR | tout est rendu à la requête (`connection()` à la racine, exigence CSP documentée) — aucun contenu stratégique derrière une exécution JS côté client |
| sitemap | contenu PUBLISHED uniquement, vide tant que non indexable — un sitemap est un acte de publication |
| HTML sémantique | `h1` unique, sections `aria-labelledby`, FAQ en `details/summary`, breadcrumbs |
| JSON-LD | `BreadcrumbList` seul, avec un commentaire qui refuse explicitement de fabriquer `Organization`/`AggregateRating` sans données réelles — **ce principe est un actif GEO, pas un manque** |
| performance | tests navigateur réels (overflow, tap targets, hydration), CSP par nonce |
| honnêteté du contenu | la section « D'où viennent les chiffres » et la FAQ existante sont exactement ce qu'un moteur de réponse veut citer |

### Les manques factuels

| manque | où |
|---|---|
| aucune donnée d'organisation (`organization_schema: false`, « no real organisation data supplied yet ») ; le bandeau porte encore « Marque et coordonnées à confirmer » | config + décision propriétaire |
| pas de `FAQPage` JSON-LD alors qu'une vraie FAQ existe | `web/components/home/Sections.tsx` |
| OpenGraph minimal sur les articles (ni `og:image`, ni `og:url`, ni `og:site_name`) ; aucun OG sur l'accueil | `web/app/[slug]/page.tsx`, `web/app/layout.tsx` |
| sitemap sans les routes statiques (`/demande-etude`, `/outils/estimation-solaire`, pages légales) | `web/app/sitemap.ts` |
| pas de `llms.txt` | `web/public/` |
| inventaire de contenu publiable : **~0** — le premier article attend l'approbation du propriétaire | pipeline |
| aucune page ni aucun mot sur le financement | tout le site |

## 2. La mesure qui commande le calendrier

La politique d'affirmations a été confrontée au vocabulaire exact du nouveau
positionnement (`requirements_for`, profil SOLAR_BE, 2026-08-31) :

```
GENERAL      LOW   ANY        « Installez des panneaux solaires sans apport initial en Belgique. »
GENERAL      LOW   ANY        « L'installation s'autofinance grâce aux économies réalisées. »
GENERAL      LOW   ANY        « Vos économies d'électricité couvrent la mensualité du financement. »
GENERAL      LOW   ANY        « Panneaux solaires gratuits : vous ne payez rien. »
GENERAL      LOW   ANY        « …accessible aux petits revenus, sans économies de départ. »
ELIGIBILITY  HIGH  OFFICIAL   « Selon votre éligibilité, seuls des frais de dossier d'environ 150 €… »
ELIGIBILITY  HIGH  OFFICIAL   « Vous êtes éligible au financement sans apport si vous êtes propriétaire. »
```

**« Gratuits : vous ne payez rien » — la formulation que le propriétaire nomme
lui-même comme dangereuse — classe GENERAL / LOW / ANY.** `_GUARANTEED_OUTCOME`
ne connaît que `garanti*` ; `forbidden_phrases` contient « gratuit à 100% » mais
ni « gratuit », ni « sans apport », ni « autofinanc* », ni « 0 € », ni « sans
rien payer ». Les portes qui ont retenu quatre affirmations HIGH sur un guide de
rentabilité laisseraient passer une promesse de gratuité sans sourciller.

Et le couple ELIGIBILITY/OFFICIAL montre le second problème : l'éligibilité à
**notre propre offre** exigerait une source OFFICIELLE — qui n'existera jamais,
puisque la source, c'est nous. La politique actuelle connaît les faits de
**tierce partie** (primes, tarifs, prix de marché) ; elle n'a **aucune notion de
fait de première partie** (notre offre, nos frais, nos conditions).

D'où les deux pièces P0 : fermer le trou de vocabulaire, et créer le canal par
lequel un fait d'offre validé peut légitimement entrer dans une page.

## 3. Le suspens juridique — À VALIDER PAR UN JURISTE, avant toute publication

Une page « sans apport / financement / mensualités » est, selon le montage,
de la **publicité pour un crédit à la consommation** ou y conduit. En Belgique
(livre VII du Code de droit économique — références exactes à faire confirmer) :

- la publicité pour un crédit à la consommation impose des **mentions légales
  obligatoires**, dont le slogan « *Attention, emprunter de l'argent coûte aussi
  de l'argent.* », et encadre l'affichage des taux et exemples chiffrés ;
- présenter, comparer ou faciliter l'obtention d'un crédit peut relever du
  statut d'**intermédiaire de crédit**, soumis à inscription FSMA ;
- « gratuit », « 0 € », « s'autofinance » sont des allégations que le droit des
  pratiques du marché sanctionne si les conditions réelles ne les portent pas —
  ce que le propriétaire a lui-même signalé.

Ce dépôt a déjà le bon mécanisme pour ce genre de dépendance :
`pending_legal_review`, qui bloque la sortie de staging d'un texte non validé.
**Le contenu financement doit naître avec ce drapeau levé**, et le juriste doit
répondre à trois questions : qui est le prêteur ; quel est le statut de
BEAVER DATA GROUP / Mon Projet Solaire dans le montage ; quelles mentions la
landing doit porter. Rien de tout cela n'est du code.

## 4. Gap analysis priorisée

Effort : S < 1 j · M 1–3 j · L > 3 j. Chaque entrée : problème → impact →
modification → fichiers → effort → risque → critère de vérification.

### P0 — indispensable, avant tout contenu financement

**P0.1 — Fermer le trou de vocabulaire des promesses de financement**
- *Problème* : « gratuit / sans apport / s'autofinance / 0 € » classent GENERAL/LOW (mesuré §2).
- *Impact* : sans cela, le pipeline peut générer et laisser passer la formulation la plus dangereuse du positionnement.
- *Modification* : catégorie `FINANCING_PROMISE` (HIGH) dans `claim_categories` + extension de `forbidden_phrases` (« gratuit », « 0 €", « sans rien payer », « s'autofinance » nu — la forme conditionnelle sourcée restant permise) + extension `_GUARANTEED_OUTCOME` aux formes « autofinanc\* », « couvre la mensualité ». Mutations comprises, méthode avant/après sur le registre scellé (199 affirmations) comme pour `eur`-dans-*chaleur*.
- *Fichiers* : `config/verticals/solar_be.yaml`, `app/services/claim_policy.py`, tests.
- *Effort* : S–M. *Risque* : faux positifs sur la prose « rentable » — mesurer avant, comme le palier A/B l'a montré.
- *Vérification* : les 8 phrases du §2 classent HIGH ou tombent en `FORBIDDEN_PHRASE` ; 0 changement non voulu sur le registre scellé.

**P0.2 — Registre d'offre de première partie, versionné**
- *Problème* : les faits de l'offre (frais de dossier ~150 €, conditions, zones, critères) n'ont aucun canal légitime : la recherche ne peut pas les établir, et le rédacteur n'a pas le droit d'inventer.
- *Impact* : c'est le socle de TOUT le positionnement — landing, FAQ, hero, schema `Offer`, futurs outils MCP. Un seul endroit, une seule vérité, versionnée.
- *Modification* : bloc `offer:` dans la config du site (ou fichier dédié), sur le modèle exact des textes de consentement : chaque fait porte une **version**, un drapeau `pending_legal_review`, et une date de validation propriétaire. Le brief/rédacteur reçoit ces faits comme `first_party_facts`, distincts des faits de recherche ; la QA vérifie que tout chiffre d'offre dans un brouillon vient du registre, à la version près.
- *Fichiers* : `config/sites/solar_be.yaml`, `app/site/config.py`, `app/services/brief_service.py`, `app/services/qa_service.py`, tests.
- *Effort* : M. *Risque* : faible — mécanique déjà éprouvée par les consentements.
- *Vérification* : un brouillon citant un montant d'offre absent du registre est bloqué ; un fait `pending_legal_review: true` ne peut pas atteindre une page servie.

**P0.3 — Les trois questions au juriste (§3)**
- *Effort code* : nul. *Critère* : réponses écrites, versionnées dans le registre P0.2. **Bloque la publication de la landing, pas sa préparation.**

**P0.4 — Données d'organisation : décision propriétaire**
- *Problème* : `organization_schema: false` faute de données ; le bandeau dit encore « Marque et coordonnées à confirmer ». Sans entité déclarée, aucun graphe d'entités, aucun `Organization`/`LocalBusiness`, et un LLM ne peut pas répondre « qui est Mon Projet Solaire ».
- *Modification* : le propriétaire fournit : dénomination légale vs marque (BEAVER DATA GROUP / Mon Projet Solaire / Solar Belgium — trois noms coexistent aujourd'hui), n° BCE, adresse, zone d'intervention, téléphone public ou non, certifications réelles (RESCert du partenaire installateur ?). Puis `organization_schema: true` et P2.1.
- *Effort* : S (côté code). *Critère* : un seul nom public cohérent sur bandeau, footer, confidentialité et schema.

### P1 — fort impact SEO / conversion

**P1.1 — Landing « Installer des panneaux solaires sans apport en Belgique »**
- *Problème* : l'intention « sans apport / financement » n'a aucune page ; c'est le cluster le moins concurrentiel et le plus différenciant de la liste.
- *Modification* : route statique `/panneaux-solaires-sans-apport` (contenu d'offre = première partie, donc **hors pipeline de recherche**, écrit depuis le registre P0.2), structure = les 10 points demandés : coût réel → solutions de financement → ce qui est réellement avancé → frais de dossier → économies estimées (avec la discipline existante : pas de montant non sourcé — la page peut expliquer la **méthode** mensualité vs économie sans inventer de chiffre tant que l'exemple chiffré validé n'existe pas) → conditions d'autofinancement → exemple chiffré réaliste (fourni et validé par le propriétaire, jamais généré) → éligibilité → CTA simulation. Mentions légales du §3. Meta title/description dédiés, `FAQPage` JSON-LD sur ses questions.
- *Fichiers* : `web/app/panneaux-solaires-sans-apport/page.tsx`, `web/app/sitemap.ts`, config.
- *Effort* : M. *Risque* : juridique (§3) — la page naît `pending_legal_review`.
- *Vérification* : la page ne contient aucun chiffre absent du registre ; la garde de staging bloque tant que le juriste n'a pas validé ; les phrases-tests du §2 n'y apparaissent sous aucune forme non conditionnelle.

**P1.2 — Le positionnement dans l'existant**
- *Hero* : une ligne d'accroche secondaire (« Un projet solaire n'exige pas d'épargne préalable : selon votre situation, le financement peut se rembourser par vos économies d'électricité — on vous montre comment, chiffres à l'appui ») + lien vers la landing. Formulation conditionnelle, jamais promissive.
- *FAQ accueil* : +2 questions max (« Faut-il un apport ? », « L'installation peut-elle s'autofinancer ? »), réponses courtes d'abord — le format `details/summary` existant est déjà idéal AEO.
- *`default_meta_description`* : y intégrer l'axe accessibilité.
- *Formulaire de qualification* : une question `financing_interest` (OUI/NON/DÉJÀ FINANCÉ) — qualifie le lead ET mesure la demande réelle avant d'investir davantage.
- *Fichiers* : `Sections.tsx`, `config/sites/solar_be.yaml` (seo + formulaire), `web/lib/types.ts`.
- *Effort* : S–M. *Vérification* : tests navigateur existants verts ; la question apparaît dans `qualification` du lead capturé.

**P1.3 — Sitemap complet + cluster de seed keywords**
- *Sitemap* : ajouter les routes statiques publiques (toujours derrière `indexable`).
- *Seeds* : les 11 requêtes de la liste entrent comme seed keywords du pipeline **après P0.1/P0.2** — les portes existantes (substance N=8, arbitrage, relance bornée) s'appliquent telles quelles. Les requêtes purement « offre » (sans apport, mensualités) pointent vers la landing plutôt que vers un article de recherche ; les requêtes mixtes (« panneaux solaires financement Belgique ») passent par le pipeline.
- *Effort* : S. *Vérification* : sitemap liste les statiques quand `indexable` ; chaque seed a soit une page cible, soit un run de pipeline tracé.

### P2 — GEO / AEO / LLM

**P2.1 — JSON-LD étendu, sans rien fabriquer**
- `FAQPage` sur la FAQ accueil et la landing (contenu déjà réel) ; `Organization` + `LocalBusiness` dès P0.4 ; `Service`/`Offer` **uniquement** depuis le registre P0.2 ; `Article` (+dates) sur le contenu publié ; `Review`/`AggregateRating` : **refusés tant qu'il n'existe pas d'avis vérifiables** — le commentaire du code qui dit « structured data that asserts things nobody supplied is fabrication with a schema » est la bonne politique et il reste.
- *Fichiers* : `layout.tsx`, `Sections.tsx`, `[slug]/page.tsx`, landing. *Effort* : M.
- *Vérification* : Rich Results Test sans erreur ; chaque nœud du graphe (`@id`) référencé de façon cohérente entre pages ; zéro propriété sans donnée réelle.

**P2.2 — Réponse courte d'abord, partout**
- Le pipeline a déjà `core_question` / `must_answer_directly` ; l'étendre du prix aux questions du cluster (« Peut-on…? Combien faut-il avancer…? ») pour que chaque page publiée ouvre sur 2–3 phrases factuelles citables, puis le détail. Les 8 questions listées deviennent des seeds ou des sections de la landing selon qu'elles sont recherche ou offre.
- *Effort* : S–M. *Vérification* : chaque page publiée porte une réponse ≤ 50 mots avant le premier `h2`.

**P2.3 — `llms.txt`**
- Généré, pas statique : même porte que le sitemap (vide/absent tant que non indexable), listant l'identité (P0.4), l'offre (P0.2, post-juriste) et le contenu publié. `llms-full.txt` seulement si le volume le justifie un jour. Complément, pas substitut, des fondamentaux — qui sont déjà sains ici.
- *Fichiers* : `web/app/llms.txt/route.ts`. *Effort* : S. *Vérification* : 404/refus tant que `indexable=false` ; contenu = uniquement du publié.

**P2.4 — OpenGraph complet** : `og:url`, `og:site_name`, `og:image` (exige un visuel de marque — propriétaire), `article:published_time`. *Effort* : S.

**P2.5 — Autorité et citations — post-bascule, off-site**
- Annuaires belges pertinents, certifications réelles (celles du partenaire installateur, nommé), témoignages **réels et datés** seulement, étude de cas chiffrée = une installation réelle du partenaire avec factures. Pages auteur : exigent un humain nommé — décision propriétaire. Les chiffres tiers continuent de citer l'officiel (CWaPE, régulateurs) — le registre d'autorités existe déjà.
- *Effort* : continu, majoritairement hors code. *Vérification* : chaque citation externe pointe vers une page qui existe et dit ce qu'on lui fait dire.

### P3 — architecture agentique / MCP

**P3.1 — La distinction demandée, actée** : SEO/GEO/AEO = être trouvé et cité (P0–P2) ; MCP/API = être **utilisé** par un agent. On n'implémente pas un MCP pour le SEO.

**P3.2 — Architecture proposée** (design d'abord, comme le contrat v2 — un document, pas du code) :

```
web (Next) ─┐
            ├─→ FastAPI existante (couche métier : config, offres, leads, events)
MCP server ─┘        │
  (adaptateur mince) └─→ PostgreSQL
```

- Le serveur MCP n'a **aucune logique métier** : il expose ce que l'API sait déjà faire, plus deux lectures nouvelles (offres, zones) qui sortent du registre P0.2.
- Outils, mappés sur l'existant : `get_solar_offers` / `get_financing_options` / `check_service_area` ← registre d'offre ; `request_solar_quote` ← route leads existante **avec la sémantique de consentement intégrale** — un agent qui transmet un lead transmet les réponses par cas `(purpose, channel)`, exactement le contrat v2 déjà arbitré ; `check_financing_eligibility` / `estimate_solar_savings` / `estimate_installation_cost` : **refusés tant que** le juriste (éligibilité = quasi-offre de crédit) et la discipline de preuve (aucune estimation non vérifiable — le site lui-même refuse d'en afficher) ne sont pas résolus ; `book_consultation` : exige un agenda qui n'existe pas.
- Gardes propres aux agents : authentification par clé (le pot de miel ne s'applique pas), quotas, journalisation de l'agent appelant dans l'attribution du lead, et l'interdiction d'écrire vers techformanord inchangée.
- *Effort* : design M, implémentation L. *Vérification du design* : chaque outil énumère ce qu'il refuse et pourquoi, avant ce qu'il rend.

## 5. Plan d'implémentation par phases

| phase | contenu | dépend de | livrable de sortie |
|---|---|---|---|
| **0 — Gardes et intrants** | P0.1 (vocabulaire, mesuré, muté), P0.2 (registre d'offre), collecte P0.4, questions P0.3 posées | rien | les 8 phrases du §2 bloquent ; registre vide mais mécanisé |
| **1 — Contenu et parcours** | P1.1 landing (`pending_legal_review`), P1.2 hero/FAQ/meta/question formulaire, P1.3 sitemap+seeds | phase 0 | landing complète en staging, bloquée par la garde légale |
| **2 — GEO/AEO** | P2.1 JSON-LD, P2.2 réponse-d'abord, P2.3 llms.txt, P2.4 OG | P0.4 pour Organization ; sinon indépendant | Rich Results propre ; llms.txt derrière la porte |
| **3 — Bascule et autorité** | levée de `pending_legal_review` (juriste), **bascule publique (propriétaire)**, puis P2.5 off-site | validation juridique + mot du propriétaire | site indexable, campagne de citations lancée |
| **4 — Agentique** | P3.2 en document d'architecture, arbitrage, puis implémentation | phases 0–3 (chaque réponse d'outil est une déclaration d'offre) | doc d'architecture soumis avant toute ligne de code |

Chaque phase suit la discipline en vigueur : branche + PR, mesure avant
affirmation, mutations sur les gardes, rien ne se publie sans le mot du
propriétaire.

## 6. Ce qui n'appartient qu'au propriétaire

1. La **bascule publique** — sans elle, tout ceci est de l'énergie potentielle.
2. Les **données d'organisation** (P0.4) et la levée du « Marque et coordonnées à confirmer ».
3. Les **faits d'offre** : les 150 €, les conditions, l'exemple chiffré réaliste — fournis, pas générés.
4. La **validation juridique** du §3.
5. L'**approbation** du premier article, toujours PENDING — l'inventaire de contenu commence là.
