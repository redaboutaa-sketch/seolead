# PRISE EN MAIN — consentement v2 et formulaire NL : préparation de la mécanique

**Date :** 2026-08-29
**Branche :** `claude/seolead-consent-v2-form-zs96bs` (depuis `main` @ `5c1a6fa`)
**Référence :** audit externe du 2026-08-30 (consentement de canal absent,
politique excluant la transmission au partenaire)
**Bases mesurées avant tout changement :** backend `709 passed / 7 skipped` ;
web `51 passed / 16 skipped`, `tsc` et `eslint` propres.
**Après :** backend `721 passed / 7 skipped` ; web `56 passed / 16 skipped` ;
`next build` sert `ƒ /nl/demande-etude` ; replay migrations `8↑ / 8↓ / 8↑` sur
un PostgreSQL 16 jetable.

Les interdits ont tenu : aucun texte de consentement existant ni la politique
de confidentialité modifiés ; `noindex,nofollow` et le bandeau de préproduction
en place ; aucun secret ; aucune écriture vers techformanord.

---

## Pièce 1 — l'audit externe, vérifié de l'intérieur

| Affirmation de l'audit | Verdict | Mesure |
|---|---|---|
| `captured_lead` à 0 ligne | **NON RE-MESURABLE D'ICI** | Ce clone n'a pas d'accès à la base déployée. Dernière mesure interne consignée : **0** (`PHASE5A_LEAD_DESTINATION_REPORT.md` §2, 2026-08-13). Cohérent avec un producteur non configuré et un site noindex — mais je ne confirme pas ce que je ne peux pas compter. |
| Adaptateur prospect360 complet | **CONFIRMÉ** | `app/site/prospect360_destination.py` (charge canonique + classification 201/200/409/401/429/5xx), machine d'états dans `app/services/lead_export.py` (identité frappée et gelée AVANT tout HTTP, rejeu de la copie gelée, 409 jamais succès), CLI `seolead leads export`, migration `0007`. La suite `tests/test_lead_export.py` couvre charge, rejeu, conflit, fenêtre de panne et non-fuite des secrets. |
| Deux variables d'environnement absentes | **CONFIRMÉ, précisé** | Quatre alias existent (`PROSPECT360_INGEST_URL`, `PROSPECT360_CREDENTIAL`, `PROSPECT360_TIMEOUT_SECONDS=30`, `PROSPECT360_MAX_ATTEMPTS=5`). Les **deux porteuses** ont un défaut vide ⇒ `prospect360_configured = False` ⇒ le CLI refuse d'exporter (`app/cli.py:677`). Écart relevé en plus : **aucune des quatre n'est documentée dans `.env.example`** — le jour J, l'opérateur ne les trouvera pas là où tout le reste est. |
| Preuve de consentement stockée | **CONFIRMÉ, trois précisions** | Champs exacts sur `captured_lead` : `consent_marketing` (bool), `consent_version` (« solar-be-consent-v1.0-2026-08-17 », copiée de la config à la capture), `consent_timestamp` (instant **serveur** de la capture, UTC), `consent_source` (= `page_path`). Précisions : (1) `consent_processing` n'a **pas de colonne** — il est prouvé par l'existence de la ligne (`capture_lead` refuse sans lui) et re-exigé à l'export (`verifier_consentement`) ; (2) l'horodatage est la réception serveur, pas le clic ; (3) **une seule** version couvrait les deux cases — c'est la limite que la Pièce 2 lève. |
| Formulaire « aligné champ à champ » sur le contrat | **FAUX SUR UN POINT — corrigé** | Les sept champs Solar et toutes leurs valeurs correspondent exactement à DEC-P5A-QUAL-03/§P4 (vocabulaires, bornes, motif code postal `^[1-9][0-9]{3}$`, `UNKNOWN` = réponse). MAIS `monthly_bill_eur` était **encore collecté** (étape consumption), alors que DEC-P5A-QUAL-06 — décision finale — le supprime *entièrement* (« not collected »). L'adaptateur l'excluait de la charge, rien ne fuyait ; restait la collecte. Supprimé ici (commit `0994a18`), suppression que §P4 prescrit à l'identique. `battery_interest` reste : collecté, jamais transmis — conforme. |
| Aucun consentement de canal | **CONFIRMÉ** | Le v1 transporte `consent.{processing, version, timestamp, source}` et rien d'autre ; les champs marketing/canal sont *nommément rejetés* par le DTO (`extra: "forbid"`, tests AST côté plateforme). La case marketing locale ne nomme aucun canal (Décision 2 : intransmissible). |
| Politique excluant la transmission au partenaire | **CONFIRMÉ** | `web/app/confidentialite/page.tsx:116-127` : destinataires limités aux personnes habilitées du responsable et aux prestataires agissant *pour son compte* ; et la page du formulaire affirme « Aucune donnée n'est transmise à un tiers ». Nuance : la phrase sur les « partenaires commerciaux indépendants » (l.129-131) est conditionnelle (information préalable + consentement spécifique), pas absolue — c'est exactement le chemin que les nouveaux textes devront ouvrir. |

## Pièce 2 — N cases de consentement, chacune avec sa version

Chaque case devient une ligne de **`lead_consent`** (migration `0008`,
additive) : clé, finalité (`PROCESSING | FOLLOWUP_CONTACT | MARKETING |
PARTNER_TRANSFER`), canal éventuel (`PHONE | WHATSAPP | EMAIL | SMS` — jamais
inventé), état, **version du texte vue par le visiteur**, instant, provenance.
Un refus est un fait enregistré (`granted = false`), distinct de l'absence de
ligne (« jamais proposé »). Les colonnes héritées ne bougent pas : le contrat
v1 armé les lit.

La configuration est l'autorité : trois nouvelles cases **PLACEHOLDER
NON-VALIDÉ** (suivi téléphone, suivi WhatsApp, transmission partenaire) sont
câblées bout en bout (YAML → DTO → formulaire → API → capture), et deux
gardes-fous du chargeur tiennent la ligne : une case `pending_legal_review` ne
peut pas quitter le staging (même forme que la porte d'indexation), et une
case non-PROCESSING ne peut pas être `required` (un choix forcé n'est pas un
consentement).

**Le critère de réussite est tenu par un test** :
`test_changing_a_version_in_config_is_the_whole_change` — le jour où un texte
validé tombe, le changement est *label + consent_version + retrait du
drapeau*, par case, dans le YAML seul ; chaque nouvelle capture enregistre la
nouvelle version sans autre changement.

Mesuré : 10 tests nouveaux ; replay `8↑/8↓/8↑` sur PostgreSQL 16, `CHECK`
refusant une finalité inconnue ; charge v1 inchangée (les tests qui
l'épinglent passent tels quels).

## Pièce 3 — le formulaire néerlandais, mécanique seule

`/demande-etude` est déclarée `[fr, nl]` et **`/nl/demande-etude` existe**, en
partageant son corps avec la page française (un composant : les deux locales ne
peuvent pas diverger structurellement). Tout libellé — étapes, champs, options,
aides, chrome du formulaire, page — se résout par une chaîne de repli :
`i18n.nl` s'il existe, texte de base sinon, jamais un blanc.

Tous les libellés NL sont des **placeholders marqués « À TRADUIRE PAR UN
NATIF »** (les variantes NL des textes de consentement portent en plus « À
VALIDER JURIDIQUEMENT ») ; aucune traduction automatique nulle part.

**Le chemin de la locale est vérifié** : `locale="nl"` → `language` du POST →
validé contre `supported_languages` → `lead.language` →
`lead_attribution.language` → **`attribution.locale`** de la charge canonique
(`test_la_locale_choisie_voyage_jusqu_a_attribution_locale`) ; une langue hors
site (`de`) retombe sur `fr` plutôt que de partir telle quelle.

Limites assumées, documentées dans le code : l'en-tête/pied de page restent FR
sur `/nl` (le layout racine possède `<html lang>` et le chrome ; le rendre
dynamique par requête déferait le travail ISR/bfcache — un layout `/nl` pose
`lang="nl"` sur le contenu pour les technologies d'assistance) ; et il n'y a
toujours pas d'accueil NL — c'est du contenu, pas de la mécanique.

## Pièce 4 — proposition de contrat v2, en document

`docs/integrations/PROSPECT360_INGEST_CONTRACT_V2_PROPOSAL.md` — proposition,
rien d'implémenté, à figer avec le côté plateforme via le propriétaire :

- `consents[]` : une entrée par case offerte (finalité, canal, état, version,
  instant, provenance), refus compris ; `PROCESSING` reste obligatoire et
  `Literal[true]` ;
- `contact.contact_type: "B2C"`, `attribution.campaign` (campagne cible côté
  plateforme, configuration du site), `attribution.locale` précisée BCP-47
  langue-marché (`nl-BE`) ;
- empreinte : **v1 immuable** (arming record du 2026-08-16),
  `fingerprint_version: 2` dans la charge, `canonical_ingest_payload_v2` écrite
  À CÔTÉ de la v1, tableau canonicalisé trié par `(purpose, channel)`, golden
  test v2 épinglé dans le même commit, armement v2 selon la même règle que v1 ;
- les écarts de vocabulaire plateforme sont nommés (deux finalités sans type
  dans `consent_records`) — décisions propriétaire, pas les nôtres.

---

## Ce qui reste suspendu aux textes juridiques — nommément

1. **Texte du consentement « suivi de la demande par téléphone »**
   (`consent_followup_phone`) — placeholder `v0.0-NON-VALIDE`.
2. **Texte du consentement « suivi de la demande par WhatsApp »**
   (`consent_followup_whatsapp`) — placeholder `v0.0-NON-VALIDE`.
3. **Texte du consentement « transmission au partenaire »**
   (`consent_partner_transfer`) — placeholder `v0.0-NON-VALIDE` ; et son
   caractère obligatoire ou non, décision à prendre avec le texte.
4. **Texte marketing nommant un canal** — la case actuelle (« offres et
   conseils ») ne nomme aucun canal et reste intransmissible (Décision 2) ;
   seule une reformulation validée la rendra exportable.
5. **La politique de confidentialité** — la section « Destinataires » exclut le
   partenaire, et la page du formulaire affirme « Aucune donnée n'est transmise
   à un tiers » : les deux doivent changer AVANT toute activation de la
   transmission. Textes en validation, intouchés ici.
6. **Les variantes néerlandaises des textes de consentement** — textes
   juridiques à part entière : traduction par un natif ET validation ; plus la
   décision de versionnage (une version par locale, ou une version couvrant
   ses traductions — `lead_consent` porte les deux sans migration).
7. **Les libellés NL non juridiques** (champs, étapes, chrome, page) —
   traduction par un natif, sans enjeu de validation juridique.
8. **Côté contrat v2** (décisions propriétaire, pas juriste, mais bloquantes) :
   vocabulaire `consent_records` pour `FOLLOWUP_CONTACT` et `PARTNER_TRANSFER`,
   registre des identifiants de campagne, enum `contact_type`.

Le jour où les textes 1–5 tombent, la mécanique de ce lot les reçoit sans
changement de code : YAML pour les cases et leurs versions, pages légales pour
la politique — c'est ce que cette préparation avait à garantir.
