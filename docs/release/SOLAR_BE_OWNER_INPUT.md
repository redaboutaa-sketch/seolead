# SOLAR_BE — Données propriétaire : fournies / restantes

Version 2 (2026-08-31). La version 1 listait l'identité de l'opérateur comme
blocker — elle est FOURNIE et intégrée. Ce document tient désormais deux
registres : ce qui est acquis (ne plus le redemander), et ce qui bloque
encore, qui concerne presque exclusivement **SG Solution**.

## 1. FOURNI — intégré à la configuration (ne plus demander)

| Donnée | Valeur | Où c'est intégré | Statut |
|---|---|---|---|
| Opérateur — dénomination | Beaver Data Group | `organization.legal_name` | **SUPPLIED** |
| Numéro d'entreprise | 935097675 (SIREN) | `organization.company_number` | **SUPPLIED** |
| Adresse | 43 rue de Marquillies, 59000 Lille, FR | `organization.address` | **SUPPLIED** |
| Email | reda.boutaa.seolead@gmail.com | `organization.email` | **SUPPLIED** |
| Téléphone | +33659855704 | `organization.phone` | **SUPPLIED** |
| Destination des leads | reda.boutaa.seolead@gmail.com | `organization.lead_destination_email` (lu par la couche de notification, jamais codé en dur) | **SUPPLIED** |
| Rôle de l'opérateur | acquisition, SEO/Prospect 360, qualification, rendez-vous, transmission | `organization.activities` + landing « Qui fait quoi » + footer | **SUPPLIED** |
| Mon Projet Solaire | marque/service exploité par Beaver Data Group (pas une entité) | footer, JSON-LD (name=marque, legalName=entité) | **SUPPLIED** |
| Offre SG Solution — les faits | 25 ans, 0,27 €/kWh fixe annoncé, 150 € uniques, panneaux+batterie, pas de crédit bancaire classique requis, rachat −4 %/an annoncé, propriété au terme, éligibilité (tarif social/amiante/électricité), alternative sans tarif | registre `sg-solution-solar-25y-v0.1-draft`, tous datés 2026-08-31 | **SUPPLIED — non publiable tant que revue juridique + validation de statut manquent** |
| Positionnement cible | panneaux + batterie, y compris difficultés d'accès au crédit / budget insuffisant | registre (owner_supplied_positioning) + pack juridique Q12 | **SUPPLIED — la formulation publique reste soumise au juriste** |

Également acquis, à ne plus vérifier : déploiement RC1, migrations 0011/0012,
vérification de production.

## 2. BLOCKERS RESTANTS — SG Solution (à fournir par le propriétaire)

Sans ces éléments, la revue juridique ne peut pas conclure et les faits
« fixe/garanti » resteront sans preuve contractuelle
(`offer.evidence.contract_reference: null`).

| # | Donnée | Utilisée pour | Statut |
|---|---|---|---|
| 1 | Dénomination légale exacte de SG Solution | mentions, consentement de transmission, JSON-LD éventuel | ______ |
| 2 | Numéro d'entreprise (BCE ou équivalent) | idem | ______ |
| 3 | Siège social | idem | ______ |
| 4 | Site web, email public, téléphone public | « qui fait quoi », mentions | ______ |
| 5 | Entité contractante avec le client final | pack juridique §1 | ______ |
| 6 | Identité de l'installateur + certifications (RESCert le cas échéant) | landing, confiance — RIEN n'est publié d'ici là | ______ |
| 7 | Rôle « fournisseur d'énergie » de SG Solution (statut/autorisations pour l'offre alternative) | pack juridique Q22 | ______ |
| 8 | Propriétaire de l'installation PENDANT le contrat | qualification juridique | ______ |
| 9 | Contrat type SG Solution | `evidence.contract_reference` — condition des formulations « fixe/garanti » | ______ |
| 10 | Conditions générales | idem | ______ |
| 11 | Formule contractuelle exacte du rachat (assiette, méthode, plancher, HT/TTC, date de calcul) | pack juridique Q19-20 — aucune projection n'est calculée sans elle | ______ |
| 12 | Preuve contractuelle du 0,27 €/kWh et du caractère fixe 25 ans | pack juridique Q13-16 | ______ |
| 13 | Preuve contractuelle du transfert de propriété au terme | pack juridique Q21 | ______ |
| 14 | Tarif de l'offre alternative (si communication souhaitée) | aujourd'hui : `fallback_offer.tariff.amount: null`, AUCUN prix généré | ______ |

## 3. Blockers restants — hors SG Solution

| # | Donnée | Utilisée pour | Statut |
|---|---|---|---|
| 15 | Revue juridique du modèle réel (matrice L-1…L-20) | lever `pending_legal_review` — voir `docs/legal/SOLAR_BE_FINANCING_REVIEW.md` | ______ |
| 16 | Décision propriétaire : approuver/rejeter `/prix-panneaux-solaires-belgique` révision 2 | premier contenu publié (portes déterministes PASS, approbation PENDING) | ______ |
| 17 | Conditions d'utilisation du site | `/conditions` (placeholder noindex) | ______ |
| 18 | Identifiants SMTP (SEOLEAD_SMTP_* dans .env de l'hôte) | livraison effective des notifications de leads | **FOURNI 2026-08-31** — relais Brevo configuré sur l'hôte, envoi accepté |
| 19 | Jetons Search Console / Bing (`seo.verification.*`) | avant l'indexation, recommandé | **FOURNIS 2026-08-31** — Google et Bing, servis en production |
| 20 | Titre « – Solar Belgium » de /confidentialite : à confirmer ou reformuler | cohérence des noms | **TRANCHÉ 2026-08-31** — le service est « Mon Projet Solaire » partout ; politique v1.2, texte de consentement v1.1. Décision prise après avoir vu ce troisième nom dans les résultats Google |

## 4. Ce que le propriétaire n'a toujours PAS à fournir

- Des chiffres « types » de production/économie : refusés par construction.
- Des données de revenus/solvabilité des visiteurs : non collectées
  (minimisation — aucun besoin à l'étape lead).
- Des secrets dans le dépôt : jamais.
