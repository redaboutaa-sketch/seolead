# Proposition — contrat d'ingestion v2 (SEO Lead Factory → Prospect 360)

**Statut : PROPOSITION. Rien ici n'est implémenté, d'aucun côté, et rien ne
doit l'être depuis ce dépôt.** Le contrat v1 est armé et immuable
(`PROSPECT360_INGEST_CONTRACT.md`, arming record du 2026-08-16T17:34:58Z) ; un
v2 ne peut se figer qu'avec le côté plateforme, via le propriétaire des deux
dépôts. Ce document existe pour que cette conversation parte d'un schéma
concret plutôt que d'une séance de conception.

## Pourquoi un v2

L'audit externe du 2026-08-30 a établi deux manques bloquants pour le parcours
aval, et le v1 ne peut porter ni l'un ni l'autre sans changer d'empreinte :

1. **Aucun consentement de canal.** Le v1 transporte exactement
   `consent.{processing, version, timestamp, source}` — le consentement au
   traitement, rien d'autre. Les décisions DEC-P5A-QUAL-03 et le DTO
   (`extra: "forbid"`, champs marketing nommément rejetés) rendent tout
   consentement de canal *irrecevable* en v1 : c'était le bon choix tant que le
   site ne collectait rien de tel, et c'est aujourd'hui le blocage.
2. **La transmission au partenaire n'est pas exprimable.** Aucun champ v1 ne
   dit « cette personne a consenti à ce que sa demande soit transmise à un
   partenaire nommé » — or c'est la finalité même du flux.

S'y ajoutent trois besoins que le v1 n'exprime pas : `contact_type` (la
plateforme sert du B2B ; ces leads sont B2C), la campagne cible côté
plateforme, et une locale porteuse du marché.

Le producteur stocke déjà ce qu'il faut : la table `lead_consent` (migration
0008 de ce dépôt) porte N cases indépendantes — clé, finalité, canal, état,
version du texte, instant, provenance. Le v2 est la projection de cette table
sur le fil.

## Schéma de charge proposé

```jsonc
{
  "external_correlation_id": "sl-…",        // inchangé, 1–128
  "source_system": "seo_lead_factory",       // inchangé, 1–64

  "contact": {
    "first_name": "…", "last_name": "…",
    "email": "…", "phone": "…",
    "job_title": null,
    "contact_type": "B2C"                    // NOUVEAU. Literal en v2 côté
                                             // producteur ; l'enum {B2C, B2B}
                                             // appartient à la plateforme.
  },

  "project": { /* les sept champs Solar de DEC-P5A-QUAL-03, inchangés */ },

  // NOUVEAU — remplace le bloc `consent` du v1. Une entrée par case OFFERTE
  // par le formulaire, accordée ou refusée. La finalité PROCESSING reste
  // obligatoire et `granted: true` (Literal), comme en v1 : un lead sans
  // consentement au traitement n'existe pas.
  "consents": [
    {
      "purpose": "PROCESSING",               // PROCESSING | FOLLOWUP_CONTACT |
                                             // MARKETING | PARTNER_TRANSFER
      "channel": null,                       // PHONE | WHATSAPP | EMAIL | SMS
                                             // | null quand le texte ne nomme
                                             // aucun canal. JAMAIS inventé.
      "granted": true,
      "text_version": "solar-be-consent-v1.0-2026-08-17",
      "timestamp": "2026-09-01T09:00:00Z",
      "source": "/demande-etude"
    },
    { "purpose": "FOLLOWUP_CONTACT", "channel": "PHONE",    "granted": true,  "text_version": "…", "timestamp": "…", "source": "…" },
    { "purpose": "FOLLOWUP_CONTACT", "channel": "WHATSAPP", "granted": false, "text_version": "…", "timestamp": "…", "source": "…" },
    { "purpose": "MARKETING",        "channel": null,       "granted": false, "text_version": "…", "timestamp": "…", "source": "…" },
    { "purpose": "PARTNER_TRANSFER", "channel": null,       "granted": true,  "text_version": "…", "timestamp": "…", "source": "…" }
  ],

  "attribution": {
    /* …les 14 champs v1, inchangés, avec deux précisions… */
    "locale": "nl-BE",                       // PRÉCISÉ : BCP-47 langue-marché.
                                             // v1 envoie `lead.language` nu
                                             // ("fr") ; le marché vient du
                                             // site, pas du visiteur.
    "campaign": "solar-be-2026-q4"           // NOUVEAU : identifiant de la
                                             // campagne cible côté plateforme.
                                             // Configuration du site, jamais
                                             // une entrée visiteur. Borne 255.
  }
}
```

**Toujours absent, et pas par oubli** (inchangé depuis v1) : `tenant_id`,
identifiants de compte de service, `score`, `monthly_bill_eur`,
`battery_interest`, tout blob libre. `extra: "forbid"` partout.

**Réponse** : inchangée (DEC-P5A-TRANSPORT-02) — `outcome`, `prospect_id`,
`external_correlation_id` ; pas de `prospect_id` sur conflit.

**Identité d'idempotence** : inchangée —
`(tenant_id, source_system, external_correlation_id)`.

### Sémantique des refus

Un refus voyage (`granted: false`) parce qu'il est une information de
conformité : une liste de suppression ne se construit pas sur des absences.
Mais la règle v1 demeure pour le traitement : il n'existe aucun moyen d'envoyer
`PROCESSING granted: false`. Ce que la plateforme *écrit* pour un refus
(un `consent_records` en `status` négatif, ou rien) est une décision côté
plateforme — le producteur affirme ce qui a été montré et répondu, pas la
politique de stockage d'en face.

### Correspondance plateforme (à trancher côté Prospect 360)

`consent_records.type` connaît `{data_processing, email_marketing,
sms_marketing, phone_marketing, cookies, profiling}`. Trois écarts à trancher
par le propriétaire, aucun par ce dépôt :

| v2 | candidat plateforme | écart |
|---|---|---|
| `PROCESSING` | `data_processing` | propre |
| `MARKETING` + canal | `email_marketing` / `sms_marketing` / `phone_marketing` | propre quand un canal est nommé ; **la case actuelle sans canal reste intransmissible** (Décision 2, inchangée) |
| `FOLLOWUP_CONTACT` + canal | **aucun type existant** — le suivi d'une demande n'est pas du marketing | vocabulaire à étendre, ou finalité portée par `purpose` |
| `PARTNER_TRANSFER` | **aucun type existant** | idem |

## Gestion d'empreinte

**v1 ne bouge pas.** L'arming record du 2026-08-16 rend le jeu de champs, la
canonicalisation et le golden digest définitifs. Toute évolution est **un v2
publié À CÔTÉ du v1, jamais par-dessus** — la règle que le contrat v1 énonce
lui-même.

- `fingerprint_version: 2`, *dans* la charge canonique, comme en v1 — deux
  versions ne peuvent pas se percuter.
- `canonical_ingest_payload_v2` est une fonction écrite à côté de
  `canonical_ingest_payload_v1`, qui n'est ni éditée ni supprimée ; les lignes
  v1 déjà en base restent interprétables à jamais.
- Champs v2 inclus : ceux du v1, plus `contact.contact_type`,
  `attribution.campaign`, et le tableau `consents` **entier** — chaque entrée
  avec ses cinq champs. Deux dépôts qui diffèrent par un seul refus de case
  sont deux dépôts différents.
- Canonicalisation du tableau : trié par `(purpose, channel)` avec `null` avant
  toute valeur, pour que l'ordre d'affichage du formulaire ne change jamais
  l'empreinte. Mêmes règles v1 pour le reste : `json.dumps(sort_keys,
  separators, ensure_ascii=False)`, absent ≡ null ≡ "" pour les optionnels,
  timestamps normalisés UTC, e-mail et téléphone par les normaliseurs canoniques
  de la plateforme.
- `TestGoldenV2` épingle le digest ET les octets canoniques d'une requête
  synthétique gelée, dans le même commit que la fonction — même discipline que
  v1. Le v2 s'arme selon la même règle : au premier des deux événements
  (route v2 atteignable par un producteur, ou première ligne persistée), et un
  arming record v2 est écrit dans le contrat.
- Transport : le v1 reste servi tel quel pour toujours ; le v2 est une
  évolution du DTO discriminée côté plateforme (nouvelle version de route ou
  champ de version — au choix du propriétaire ; `extra: "forbid"` garantit
  déjà qu'une charge v2 sur le DTO v1 est un 422, pas une confusion).

## Côté producteur (ce dépôt), le jour où le contrat se fige

Rien n'est à inventer : `construire_charge` v1 est gelée et une
`construire_charge_v2` la rejoint à côté — projection de `lead_consent` vers
`consents[]`, `contact_type` constant, `campaign` et le marché de la locale
depuis la configuration du site. Les charges déjà gelées en base
(`export_payload`) restent des charges v1 et se rejouent en v1 : une identité
frappée ne change jamais de version.

## Préconditions non techniques — bloquantes

1. **Textes de consentement validés** pour `FOLLOWUP_CONTACT` (par canal),
   `MARKETING` (canal nommé), `PARTNER_TRANSFER` — aujourd'hui des placeholders
   `pending_legal_review` que le chargeur refuse de laisser quitter le staging.
2. **Politique de confidentialité mise à jour** : la page publiée exclut
   aujourd'hui la transmission (« accessibles uniquement… », et la page du
   formulaire affirme « Aucune donnée n'est transmise à un tiers »). Déposer un
   lead `PARTNER_TRANSFER granted: true` pendant que le site affirme cela
   serait une contradiction publiée. Textes en validation — hors de portée de
   ce dépôt.
3. **Décisions propriétaire** : vocabulaire `consent_records` (deux finalités
   sans type), registre des identifiants de campagne, sémantique de la version
   d'un texte traduit (une version par locale, ou une version couvrant ses
   traductions validées — la table `lead_consent` porte les deux sans
   migration).

---

## Addendum du 2026-08-30 — arbitrages rendus par techformanord

Quatre des questions ouvertes ci-dessus sont tranchées. Elles sont consignées
ici comme **décisions**, pas comme propositions. Le contrat n'est pas figé pour
autant : rien n'est implémenté tant que le digest golden v2 n'existe pas.

### 1. `consents[]` retenu

Structure de liste, avec **unicité sur le couple `(purpose, channel)`** au
niveau du DTO — un doublon est un 422, pas un dernier-gagne silencieux.

L'ordre est déterministe et fait partie de la charge canonique : la règle
« null avant valeur » devient une **clé de tri explicite**, pas un effet de bord
du tri de Python sur des types mixtes. Concrètement, la clé est
`(purpose, channel is not None, channel or "")` : une entrée sans canal précède
les entrées canalisées de la même finalité, et celles-ci s'ordonnent par nom de
canal. Une finalité sans canal (`PROCESSING`, `PARTNER_TRANSFER`) et une
finalité canalisée (`FOLLOWUP_CONTACT:PHONE`) ne peuvent donc jamais permuter
d'une exécution à l'autre.

Sans cela, l'ordre d'affichage du formulaire changerait l'empreinte — la
défaillance exacte que la règle de tri des clés de qualification v1 évite déjà.

### 2. Un `PARTNER_TRANSFER` refusé n'est jamais un rejet

Le lead est **ACCEPTÉ**. Le refus est **enregistré**, et le lead est **marqué
non transmissible** côté plateforme.

C'est la bonne décision et elle mérite d'être dite : rejeter en 4xx un
visiteur qui a consenti au traitement mais pas à la transmission ferait
disparaître de la base un lead parfaitement légitime, et transformerait un choix
de l'utilisateur en erreur d'intégration. Le producteur n'a rien à faire de
particulier : il envoie ce qui a été coché, y compris les refus.

### 3. Route distincte, aucun champ de version dans le corps

`POST /api/v2/lead-ingest`. Le discriminant est l'URL.

La raison est structurelle : ajouter un `contract_version` au corps obligerait
chaque DTO à l'accepter, donc à percer `extra: "forbid"` des deux côtés. Une
charge v2 postée sur la route v1 doit rester un 422 franc, pas une négociation.
Le `fingerprint_version` **reste dans la charge canonique** — il y est une
identité de condensé, pas un champ de protocole, et il continue de garantir
qu'un digest v1 et un digest v2 ne peuvent pas se confondre même à contenu
identique.

### 4. Les refus voyagent

`granted: false` est transmis. La plateforme étend son statut avec **`refused`**,
distinct de **`revoked`**.

Cette distinction est celle que la table `lead_consent` porte déjà : une ligne
`granted=false` est un refus au moment de la collecte ; une révocation est un
retrait ultérieur d'un consentement qui avait été donné. Les confondre rendrait
impossible de répondre à « cette personne a-t-elle jamais consenti ? », qui est
la question qu'un régulateur pose.

### Ce qui reste ouvert

- Le registre des identifiants de campagne.
- La sémantique de version d'un texte traduit (une version par locale, ou une
  version couvrant ses traductions validées). Le NL n'étant pas encore traduit,
  la question n'est pas urgente — mais elle doit être tranchée **avant** la
  première charge portant une locale `nl`.
- Le digest golden v2 et son arming record.
