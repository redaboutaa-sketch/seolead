# SOLAR_BE — Données propriétaire requises avant publication

**Statut : À REMPLIR par le propriétaire.** Ce document est la liste exhaustive
des données que le système attend du propriétaire. Aucune valeur n'a été
inventée : chaque champ vide ci-dessous est vide dans la configuration
(`config/sites/solar_be.yaml`), et le site est construit pour rester
non-publiable tant que les champs marqués REQUIS ne sont pas fournis.
Remplir ce document ne publie rien : les valeurs doivent ensuite être
reportées dans la configuration, puis les portes du runbook
(`SOLAR_BE_PUBLICATION_RUNBOOK.md`) franchies dans l'ordre.

Légende — **REQUIS** : la publication est bloquée sans lui. **OPTIONNEL** :
le site fonctionne sans, la fonctionnalité correspondante reste silencieuse.
**Public** : la valeur apparaîtra sur le site ou dans son balisage.
**Valid. juridique** : la valeur doit passer par la revue juridique
(`docs/legal/SOLAR_BE_FINANCING_REVIEW.md`) avant d'être servie.

## 1. Identité de l'organisation (`organization:`)

| Champ | Statut | Où c'est utilisé | Public | Valid. juridique | Valeur à fournir |
|---|---|---|---|---|---|
| `legal_name` | REQUIS pour le schéma Organization ; sans lui, aucun schéma n'est émis | JSON-LD Organization/LocalBusiness, cohérence des mentions | Oui | Non, mais voir Q10 du pack juridique (trois noms coexistent) | ______ |
| `bce_number` | REQUIS pour le schéma Organization | JSON-LD `identifier`, mentions légales | Oui | Non | ______ |
| `address.street` / `postal_code` / `city` | REQUIS pour LocalBusiness (le schéma local reste muet sans adresse complète) | JSON-LD LocalBusiness | Oui | Non | ______ |
| `phone` **ou** `email` | REQUIS pour LocalBusiness (l'un des deux) | JSON-LD, page contact | Oui | Non | ______ |
| `service_areas` | OPTIONNEL | JSON-LD `areaServed`, ciblage éditorial | Oui | Non | ______ |
| `logo_path` | OPTIONNEL | JSON-LD `logo`, og:image | Oui | Non | ______ |
| `installer_partner` | OPTIONNEL | Page « méthode », confiance | Oui | Oui si présenté comme partenaire contractuel | ______ |
| `certifications` | OPTIONNEL | Réassurance (RESCert, etc.) — publiées seulement si vérifiables | Oui | Non | ______ |
| `same_as` | OPTIONNEL | JSON-LD `sameAs` (profils officiels) | Oui | Non | ______ |

**Décision propriétaire ouverte — les trois noms.** BEAVER DATA GROUP (responsable
de traitement dans la politique de confidentialité), Mon Projet Solaire (marque
du site), Solar Belgium (titre de la page confidentialité). Le schéma
Organization ne sera émis qu'avec UN `legal_name` assumé ; la relation
marque ↔ entité légale doit être énoncée quelque part de public (footer ou
mentions). À trancher : ______

## 2. Registre d'offre (`offer:`) — chaque fait, avec sa date

Le registre est la SEULE source de ce que le site peut affirmer sur l'offre.
Un fait sans valeur **et** sans date de validation n'existe pas pour le site ;
la QA bloque tout chiffre d'offre qui n'y figure pas. « Ne mets PAS 150
uniquement parce que cela apparaît dans notre brief. »

| Fait (`facts[].id`) | Statut | Où c'est utilisé | Public | Valid. juridique | Valeur | validated_at | valid_from/valid_until |
|---|---|---|---|---|---|---|---|
| `application_fee_eur` | REQUIS si des frais de dossier existent ; sinon écrire explicitement 0 | Landing §4 (« frais de dossier de X € »), FAQ | Oui | **Oui** | ______ | ______ | ______ |
| `upfront_payment_required` | REQUIS (true/false) | Cohérence du discours « sans apport » | Oui | **Oui** | ______ | ______ | ______ |
| `financing_term_months` | OPTIONNEL (requis si l'exemple chiffré est publié) | Exemple chiffré | Oui | **Oui** | ______ | ______ | ______ |
| `monthly_instalment_example_eur` | OPTIONNEL (requis si l'exemple chiffré est publié) | Exemple chiffré | Oui | **Oui** | ______ | ______ | ______ |
| `financing.provider` | REQUIS pour la revue juridique (identité du partenaire financier) | Pack juridique Q1 ; publication du nom = décision distincte | À décider | **Oui** | ______ | — | — |
| `worked_example` | OPTIONNEL — UNE installation réelle (production, mensualité, économie constatée), jamais générée | Landing §5 (formule remplie) | Oui | **Oui** | ______ | ______ | — |
| `eligibility.criteria` | OPTIONNEL (la landing énonce déjà les critères génériques) | Landing §8 | Oui | Oui | ______ | — | — |
| `geography.service_areas` | OPTIONNEL | Landing, JSON-LD | Oui | Non | ______ | — | — |

Puis, dans l'ordre et sans sauter d'étape :

1. `offer.version` : passer de `solar-be-offer-v0.1-draft` à une version
   assumée (ex. `solar-be-offer-v1.0`).
2. `offer.status: validated` + `owner_validated_at: <date ISO>` — l'acte
   explicite du propriétaire.
3. La revue juridique remplit `legal.reviewed_at`, `legal.reviewer`,
   `legal.mandatory_disclosures` et lève `pending_legal_review` (voir pack
   juridique). **Les deux verrous sont indépendants ; il faut les deux.**
4. Tout changement ultérieur d'une valeur = NOUVELLE version + entrée dans
   `history` (le chargeur refuse la réécriture silencieuse).

## 3. SEO / consoles (`seo.verification:`)

| Champ | Statut | Où c'est utilisé | Public | Valeur |
|---|---|---|---|---|
| `verification.google` | OPTIONNEL mais recommandé AVANT l'indexation (prouve la propriété, n'indexe rien) | balise `google-site-verification` | Oui (balise) | ______ |
| `verification.bing` | OPTIONNEL | balise `msvalidate.01` | Oui (balise) | ______ |

À copier depuis Google Search Console / Bing Webmaster Tools (méthode
« balise HTML », valeur `content` uniquement). Jamais inventés.

## 4. Textes légaux du site

| Élément | Statut | Où | Valid. juridique |
|---|---|---|---|
| Conditions d'utilisation | REQUIS avant indexation de `/conditions` (la page affiche « texte légal en attente » et reste noindex en dur) | `/conditions` | Oui |
| Mentions légales complètes (éditeur, siège, BCE, contact) | REQUIS avant publication | footer / page dédiée | Oui |
| Politique cookies | OPTIONNEL tant qu'aucun cookie non essentiel n'existe (état actuel : aucun) | `legal.cookie_policy_path` (null) | Oui si ajoutée |

## 5. Ce que le propriétaire n'a PAS à fournir

- Les chiffres de production/économie « types » : le site refuse par
  construction d'en afficher sans étude — ne pas en fournir de génériques.
- Les jetons ou clés d'API : aucun secret ne va dans le dépôt.
- Les textes de la landing : écrits, sous politique d'affirmations ; c'est la
  revue juridique qui tranche leur maintien, pas une réécriture propriétaire.
