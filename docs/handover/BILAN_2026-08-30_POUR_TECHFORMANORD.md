# Bilan seolead du 2026-08-30 — à destination du projet techformanord

Ce document est un transfert d'état, écrit depuis le dépôt `seolead` pour l'équipe
qui tient la plateforme d'acquisition. Il dit ce qui a changé côté site, ce que
cela implique pour l'ingestion, et ce qui reste à décider — chez vous comme chez
nous.

**Aucune écriture vers techformanord n'a été faite aujourd'hui**, ni en test ni en
production. L'interdit posé au départ de la journée est resté tenu de bout en
bout. Le site n'a envoyé aucun lead, pour la raison mesurée au § 4.

---

## 1. Ce qui a changé et qui vous concerne

### 1.1 Le consentement n'est plus deux booléens

Jusqu'à aujourd'hui, un lead portait `consent_processing` et `consent_marketing`,
deux cases à cocher, une seule version de texte pour tout le formulaire.

Le modèle est maintenant **une ligne par case cochée ou refusée**, table
`lead_consent`, avec pour chacune :

| colonne | rôle |
|---|---|
| `consent_key` | identifiant stable de la case (ex. `consent_followup_contact:PHONE`) |
| `purpose` | `PROCESSING` / `FOLLOWUP_CONTACT` / `MARKETING` / `PARTNER_TRANSFER` |
| `channel` | `PHONE` / `WHATSAPP` / `EMAIL` / `SMS`, ou `NULL` |
| `granted` | `false` est un **refus enregistré**, distinct de l'absence de ligne |
| `text_version` | la version exacte du texte affiché au visiteur |
| `granted_at` | l'instant |
| `source` | d'où la case a été soumise |

Ce que cela vous apporte, quand le contrat v2 existera : vous saurez non
seulement *qu'*un visiteur a consenti, mais **à quoi**, **par quel canal**, et
**sous quel texte**. Aujourd'hui vous ne recevez que le premier tiers.

Une case peut émettre plusieurs lignes : `consent_followup_contact` est déclarée
sur `[PHONE, WHATSAPP]` et produit donc **deux lignes** pour une seule case cochée.
Un lead complet en produit **cinq**, pas quatre.

### 1.2 Les quatre textes FR sont validés, les NL ne le sont pas

Le propriétaire, responsable de traitement, a validé le 2026-08-30 quatre textes
français. Ils sont branchés, épinglés au caractère près par un test, et versionnés
selon la convention `solar-be-<cas>-v1.0-2026-08-30` :

| cas | version | canal |
|---|---|---|
| `consent_processing` | `solar-be-consent-v1.0-2026-08-17` (inchangé) | — |
| `consent_followup_contact` | `solar-be-followup-contact-v1.0-2026-08-30` | PHONE + WHATSAPP |
| `consent_marketing` | `solar-be-marketing-whatsapp-v1.0-2026-08-30` | WHATSAPP |
| `consent_partner_transfer` | `solar-be-partner-transfer-v1.0-2026-08-30` | — |

Les variantes néerlandaises portent toutes `pending_legal_review: true`. Une garde
de configuration **refuse le passage hors staging** tant qu'une locale supportée
porte ce drapeau. C'est volontaire : les libellés NL seront traduits par un
locuteur natif **puis** validés juridiquement, jamais traduits automatiquement,
une version par locale.

### 1.3 La politique de confidentialité autorise désormais la transmission

C'était le point dur de l'audit externe : la politique publiée **excluait** la
transmission à un partenaire, ce qui rendait l'ingestion vers techformanord
juridiquement infondée quel que soit l'état du code. Elle a été reprise
(version `solar-be-privacy-v1.1-2026-08-30`) : la phrase d'exclusion est retirée,
une section « Transmission à notre partenaire installateur » a été ajoutée dans les
termes validés par le propriétaire.

**La base juridique de l'ingestion existe donc maintenant.** Elle n'existait pas
hier.

### 1.4 Le formulaire est prêt à être bilingue

Les routes `/demande-etude` (fr) et `/nl/demande-etude` (nl) partagent un seul
composant : elles ne peuvent pas diverger structurellement. La locale choisie
voyage jusqu'au bout de la chaîne — `LeadForm` la soumet, l'API la valide contre
`supported_languages`, elle atterrit dans `lead_attribution.language` et, dans le
payload d'export, dans **`attribution.locale`**. Ce chemin est vérifié par test.

Côté vous : `attribution.locale` vaudra `fr` ou `nl` dès que la route NL sera
publique. Rien à changer dans v1, le champ existe déjà.

---

## 2. Le contrat v1 n'a pas bougé

- Empreinte v1 **ARMED** au `2026-08-16T17:34:58Z` — intacte, non recalculée,
  non touchée.
- Aucun DTO modifié. `extra: "forbid"` toujours en place sur chaque modèle.
- L'adaptateur `app/site/prospect360_destination.py` est complet et testé.

**Conséquence directe :** tout le travail consentement décrit au § 1.1 est
aujourd'hui **invisible depuis techformanord**. Le payload v1 ne transporte que
`consent_processing` et `consent_marketing`. Les cases `FOLLOWUP_CONTACT` et
`PARTNER_TRANSFER`, leurs canaux et leurs versions de texte restent dans la base
seolead sans route vers vous.

C'est un choix, pas un oubli : v1 est immuable, v2 est un contrat neuf.

---

## 3. La proposition de contrat v2 vous attend

Document : `docs/integrations/PROSPECT360_INGEST_CONTRACT_V2_PROPOSAL.md`
(dépôt seolead). **C'est une proposition, rien n'est implémenté.**

Ce qu'elle propose :

- `consents[]` : une entrée par finalité × canal, avec `purpose`, `channel`,
  `granted`, `text_version`, `granted_at`.
- `contact_type: B2C` explicite.
- La campagne cible.
- `attribution.locale`.
- Empreinte : v1 reste figée, v2 obtient la sienne. Pas de migration en place,
  pas de recalcul de v1.

**Décisions qui vous appartiennent, et qui bloquent l'implémentation :**

1. Acceptez-vous `consents[]` comme structure, ou préférez-vous un aplatissement
   en champs nommés ?
2. Que doit faire l'ingestion d'un lead dont `PARTNER_TRANSFER` est **refusé** —
   rejet en 4xx, ou acceptation avec marquage « non transmissible » ?
3. Faut-il un `contract_version` explicite dans le payload, ou la version est-elle
   portée par l'URL de l'endpoint ?
4. Voulez-vous les refus (`granted: false`) ou seulement les accords ?

Tant que ces quatre points ne sont pas tranchés, écrire le code v2 serait
deviner.

---

## 4. Pourquoi vous n'avez encore reçu aucun lead

Trois causes indépendantes, mesurées, toutes encore actives :

**(a) Les deux variables d'environnement d'export sont absentes.**
`PROSPECT360_INGEST_URL` et `PROSPECT360_CREDENTIAL` ne sont pas définies sur le
VPS. `prospect360_configured` est donc `false` et l'export ne s'arme pas. C'est le
verrou le plus simple à lever — et il doit être levé **après** les deux autres,
pas avant.

**(b) Le site est en préproduction.** `noindex,nofollow` actif, bandeau de
préproduction affiché, `staging: true`. Aucun trafic organique n'arrive. La table
`captured_lead` compte **0 ligne**. Le passage en public est un geste distinct et
délibéré, non fait aujourd'hui.

**(c) Il n'y a pas encore de contenu publié qui puisse attirer ce trafic.**
Voir § 5.

Ordre d'allumage recommandé : contenu → passage en public → variables d'export.
Armer l'export avant d'avoir un site public reviendrait à ouvrir un robinet sur
une conduite vide, et à découvrir les erreurs d'ingestion sur les premiers vrais
leads plutôt que sur des leads de test.

---

## 5. Le pipeline de contenu — état réel

La journée a servi à déverrouiller la chaîne de production d'articles. Quatre
blocages successifs, chacun masqué par le précédent, ont été trouvés et corrigés :

| # | blocage | état |
|---|---|---|
| 1 | DataForSEO `40104` — compte non vérifié | résolu côté fournisseur |
| 2 | Plafond d'appels par fournisseur (3 alloués, 6 nécessaires) | corrigé |
| 3 | `ck_research_evidence_category` — 4 catégories de code absentes de la contrainte base depuis la Phase 3.2 | corrigé, migration `0009` (PR #11, fusionnée) |
| 4 | `DUPLICATE_TITLE` — un brouillon **rejeté** condamnait définitivement son remplaçant | corrigé, PR #12 **ouverte** |

Un pipeline complet a tourné : QA factuelle 100, QA SEO en échec sur un point
bloquant (le n° 4 ci-dessus).

**Aucun article n'est publié à ce jour.** Le premier article publiable est la
condition d'entrée de tout le reste : sans contenu, pas de trafic ; sans trafic,
pas de lead ; sans lead, l'ingestion n'a rien à ingérer.

### 5.1 La cause de fond, mesurée aujourd'hui

Sur le paquet de recherche `94eeddf1-8b6d-4247-93c0-14e0bb5d2b0d` :
**0 affirmation à risque HIGH étayée sur 57**. Quatre mécanismes identifiés,
chacun reproduit dans le code :

1. **Les sources faisant autorité sont jugées contre la mauvaise question.** La
   passe ciblée interroge des domaines officiels avec une requête dédiée, puis la
   porte de pertinence note le résultat contre la requête **d'origine** de
   l'article. 31 sources sur 40 écartées ainsi — dont la totalité de vlaanderen.be
   et de creg.be.
2. **`eur` cherché en sous-chaîne** : il figure dans *chaleur*, *onduleur*,
   *meilleur*, *heures*, *capteur*, *valeur*. Des phrases ordinaires deviennent
   des affirmations de prix de marché exigeant trois sources concordantes.
3. **`kwh` traité comme un indice de prix de l'électricité** : toute quantité
   d'énergie devient une affirmation tarifaire à risque HIGH exigeant une source
   institutionnelle datée.
4. **La détection de région retient la première sous-région de l'énumération.**
   Une page couvrant les trois régions belges — donc précisément une source
   nationale — est étiquetée wallonne, puis rejetée pour « portée régionale
   incompatible » face à une affirmation belge.

Ce n'est pas la QA qui est trop stricte : c'est l'étiquetage au-dessus d'elle qui
est faux, et qui réclame ensuite des preuves impossibles pour une étiquette
inventée.

---

## 6. Ce qui reste suspendu, et à qui

### Chez le propriétaire / le juridique

- **Traduction NL des quatre textes de consentement** par un locuteur natif, puis
  validation. Une version par locale. Bloque la route `/nl/demande-etude` et, par
  la garde de configuration, **le passage du site en public**.
- Libellés NL non juridiques du formulaire (étapes, champs, options) — même
  exigence de traduction humaine.

### Chez techformanord

- Les **quatre décisions de contrat v2** du § 3.
- L'endpoint v2 et son empreinte, si v2 est retenu.

### Chez seolead

- Fusionner PR #12 et #13.
- Corriger les quatre mécanismes du § 5.1 — trois sont des défauts non ambigus, le
  premier touche une porte de sécurité et demande un arbitrage explicite.
- Publier un premier article.
- Passage en public : `staging: false`, `allow_indexing: true`, variables web,
  en-tête Traefik, retrait du bandeau.
- Définir `PROSPECT360_INGEST_URL` et `PROSPECT360_CREDENTIAL` — en dernier.
- **Jamais fait :** une soumission de formulaire de bout en bout depuis un
  navigateur. `lead_consent` doit alors compter **5 lignes** pour un lead complet.
  Tant que ce test n'a pas eu lieu, la chaîne complète n'est prouvée que par les
  tests automatisés.

---

## 7. Références dans le dépôt seolead

| sujet | fichier |
|---|---|
| Rapport de préparation consentement v2 / NL | `CONSENT_V2_NL_PREPARATION_REPORT.md` |
| Contrat v1 (immuable, empreinte armée) | `docs/integrations/PROSPECT360_INGEST_CONTRACT.md` |
| Proposition contrat v2 | `docs/integrations/PROSPECT360_INGEST_CONTRACT_V2_PROPOSAL.md` |
| Modèle de consentement | `app/models/publication.py`, `migrations/versions/0008_lead_consent.py` |
| Résolution des cases à la soumission | `app/site/lead_capture.py` |
| Adaptateur d'export | `app/site/prospect360_destination.py` |
| Textes et versions | `config/sites/solar_be.yaml` |

Aucun secret ne figure dans ce document ni dans le dépôt : seuls des **noms** de
variables d'environnement sont cités, jamais leurs valeurs.
