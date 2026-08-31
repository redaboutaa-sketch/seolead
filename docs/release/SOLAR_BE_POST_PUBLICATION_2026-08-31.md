# SOLAR_BE — État post-publication (2026-08-31)

État daté, ajouté SANS réécrire les preuves antérieures (RC1, simulations,
runbook restent l'historique). Ce document est la référence de la phase
OPERATE → MEASURE → LEARN → IMPROVE.

## Publication

```
PUBLICATION_COMMIT   b78aa21  (PR #33 ; PR #32 = 40233f2)
DÉPLOIEMENT HÔTE     PASS (2026-08-31)
MIGRATIONS           0011 PASS · 0012 PASS · 0013 (notification leads) au prochain déploiement
staging              false
allow_indexing       true
KILL-SWITCH          seo.allow_indexing: false — incident réel uniquement
```

## URLs publiées (constatées par crawl public, 0 constat)

| URL | Statut | Indexable | Canonical | Sitemap |
|---|---|---|---|---|
| `/` | 200 | oui | ✔ | ✔ |
| `/demande-etude` | 200 | oui | ✔ | ✔ |
| `/outils/estimation-solaire` | 200 | oui | ✔ | ✔ |
| `/confidentialite` | 200 | oui | ✔ | ✔ |
| `/conditions` | 200 | **non (voulu)** — texte légal en attente | ✔ | non (voulu) |
| `/prix-panneaux-solaires-belgique` | 200 | **non — noindex figé du soft-launch (13/08)**, sort du sitemap au prochain déploiement | ✔ | jusqu'au correctif |
| `/rentabilite-panneaux-solaires-belgique` | — | (révision 2 approuvée, STAGED `80c78f22`, **publish restant**) | — | dès publication |

## URLs fermées par leur porte (état VOULU)

```
/panneaux-solaires-sans-apport → EXPECTED_GATED_404
```

Offre SG au registre, revue juridique pendante → 404, zéro lien entrant,
hors sitemap, hors llms.txt, zéro claim sensible servi. **Ce 404 n'est
jamais un incident.**

## Article — la situation exacte, deux slugs

- **Révision 2** (draft `8a1f6e46`) : APPROVED par le propriétaire
  (2026-08-31), STAGED sous le slug **de son brief** :
  `rentabilite-panneaux-solaires-belgique` (content_id `80c78f22`).
  Une commande reste : `seolead content publish 80c78f22-… --site solar_be`.
- **`/prix-panneaux-solaires-belgique`** : l'article publié au soft-launch
  du 13/08 — servi, mais noindex figé (recalculé seulement à une
  publication sur SON slug). Deux intentions de recherche distinctes
  (prix vs rentabilité) : le rafraîchissement de la page prix par le
  pipeline est le candidat contenu n° 1 dès les premières données Search
  Console.

## SMTP / Leads

```
SMTP CONFIG        PASS (HOST/USER/PASSWORD PRESENT, port 587 — aucun secret affiché)
SMTP RELAY         PASS — « lead notification delivered » (accepté par le relais Brevo,
                   jamais assimilé à « lu »)
DESTINATION        organization.lead_destination_email (config, jamais codée en dur)
PERSISTANCE        chaque lead stocké avant toute notification ; un échec ne coûte jamais le lead
ÉTAT STRUCTURÉ     migration 0013 : notification_state (SENT/FAILED/NO_TRANSPORT/
                   NO_DESTINATION) + notified_at sur chaque lead
SURVEILLANCE       `seolead leads report` — comptes par état + liste de rappel manuel
                   (tout lead ≠ SENT). Les leads antérieurs à 0013 sortent UNRECORDED.
```

## Moteurs de recherche

```
GOOGLE_VERIFICATION_TOKEN   OWNER_INPUT_REQUIRED (seo.verification.google — la balise
                            s'émet dès que la valeur existe ; rien n'est inventé)
BING_VERIFICATION_TOKEN     OWNER_INPUT_REQUIRED (seo.verification.bing)
ROBOTS                      ouvert (Allow: / ; /preview/ et /api/ exclus)
SITEMAP                     publié ; règle mécanique : jamais une page noindex,
                            jamais un draft/pending, jamais la landing fermée
LLMS.TXT                    200, gated par l'indexabilité
CONTRÔLE RÉCURRENT          sh tools/public_health_check.sh  (verdict OK/FAIL,
                            EXPECTED_GATED_404 étiqueté)
```

## Mesure SEO / GEO

- Suivi d'indexation et hebdo : `docs/seo/SOLAR_BE_INDEXATION_TRACKING.md`
  (crawlable ≠ discovered ≠ crawled ≠ indexed ≠ ranking — aucune métrique
  inventée, colonnes vides jusqu'à Search Console).
- Benchmark GEO/LLM : `docs/seo/SOLAR_BE_GEO_BASELINE.md` (protocole
  reproductible ; résultats à remplir par mesure réelle, jamais fabriqués).
- Pas de génération de contenu en masse : les 5 briefs attendent les
  premières requêtes réelles.

## Chantiers ouverts, non bloquants

1. Revue juridique des formulations SG (L-1…L-20) — seule clef de la
   landing financement.
2. Texte de `/conditions`.
3. Jetons Search Console / Bing (owner).
4. Mesure SEO continue ; surveillance des leads (`seolead leads report`).
