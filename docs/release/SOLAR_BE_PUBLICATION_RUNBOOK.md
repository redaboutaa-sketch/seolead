# SOLAR_BE — Runbook de publication (RC1 : SOLAR_BE_RC1)

Chemin unique de mise en ligne. Les portes se franchissent DANS L'ORDRE ;
chacune a un responsable, des entrées, une vérification mécanique et un état
de sortie. Aucune porte ne se franchit par défaut, par oubli ou par script :
A et B sont des actes humains, D est un acte propriétaire explicite.

**Identification RC1** : branche `chore/solar-release-candidate` (empilée sur
`feat/solar-financing-seo-geo`), marqueur `SOLAR_BE_RC1`. L'état exact du code
revu est le commit de tête de la PR RC au moment de la revue — le tag git
`SOLAR_BE_RC1` le fige si posé.

## Vue d'ensemble

```
A (propriétaire) ──▶ B (juriste) ──▶ C (QA) ──▶ D (bascule) ──▶ E (vérif post-publication)
     données            verdicts        vert         staging:false        mesures
                                                     puis allow_indexing
                            ◀───────────── ROLLBACK à tout moment ─────────────
```

Deux périmètres distincts que le code sépare déjà :
- **Le site vitrine** (accueil, estimation, demande d'étude, légal) : publiable
  dès A1 + C + D. Il ne parle du financement qu'au conditionnel (L-13 à L-16
  du pack juridique) — si la revue B ne les a pas encore jugés, retirer ces
  blocs est le geste conservateur avant un D anticipé.
- **La landing financement** : porte supplémentaire automatique. Elle n'est
  servie, liée, listée (sitemap) et indexable que quand
  `offer.publishable == true`, c'est-à-dire A2 **et** B accomplis. D ne la
  publie pas ; seuls A2+B le font.

## Porte A — Données propriétaire (responsable : propriétaire)

Entrée : `docs/release/SOLAR_BE_OWNER_INPUT.md` rempli.

- **A1 — identité** : `organization.legal_name`, `bce_number`, adresse,
  contact ; décision des trois noms tranchée ; conditions d'utilisation
  fournies (la page `/conditions` affiche un placeholder noindex tant
  qu'elles manquent).
- **A2 — offre** : chaque fait du registre avec valeur + `validated_at`
  (+ fenêtre de validité si l'offre est datée) ; `offer.version` assumée ;
  `offer.status: validated` + `owner_validated_at`. Sans A2, la landing reste
  fermée même après D — c'est voulu.

Vérification : `pytest -q` (les validateurs refusent un statut sans date, une
version réutilisée, un historique réécrit).

## Porte B — Revue juridique (responsable : juriste)

Entrée : `docs/legal/SOLAR_BE_FINANCING_REVIEW.md` — modèle d'affaires rempli
par le propriétaire, matrice L-1…L-16 remplie par le réviseur.

1. Appliquer les reformulations CONDITIONAL, retirer les FORBIDDEN.
2. Reporter les mentions obligatoires verbatim dans
   `offer.legal.mandatory_disclosures` (la landing les rend telles quelles).
3. Renseigner `legal.reviewed_at` + `legal.reviewer` ; passer
   `pending_legal_review: false`.

Sortie : `offer.publishable` devient vrai (avec A2). Aucune conclusion
juridique n'est prise par le développeur ; une matrice incomplète = porte
fermée.

## Porte C — QA technique (responsable : opérateur)

Sur la pile locale de pré-publication (voir en bas « Pile locale ») :

1. `pytest -q` — tout vert. `cd web && npx tsc --noEmit && npx vitest run &&
   npm run build` — tout vert.
2. Crawl réel : `python tools/seo_precrawl.py --base http://127.0.0.1:3100
   --out /tmp/precrawl_staging.md --label staging --probe
   /prix-panneaux-solaires-belgique` → **0 constat**.
3. Crawl simulé publication : relancer l'API avec
   `SEOLEAD_SITE_CONFIG_DIR=<copie avec staging: false>` (fichier suivi
   intact), vider `web/.next/cache/fetch-cache`, redémarrer le web, recrawler
   avec `--probe /panneaux-solaires-sans-apport` → **0 constat** ; la landing
   doit répondre 404 tant que A2+B ne sont pas faits, 200 après.
4. E2E navigateur (soumission du formulaire → 201 + lignes de consentement).

Référence RC1 (2026-08-31, pile locale) : 1269 tests python, 83 vitest,
crawl staging 0 constat, crawl simulation 0 constat.

## Porte D — Bascule (responsable : propriétaire — « Rien ne se publie sans le mot du propriétaire »)

Deux crans, dans cet ordre, à deux moments possibles différents :

- **D1 — servir** : `staging: false` dans `config/sites/solar_be.yaml`
  (commit + déploiement). Le bandeau de préproduction ne disparaît qu'à D2
  (il est lié à l'indexabilité) ; les pages restent noindex. Vérifier
  aussitôt : porte E, section E1.
- **D2 — indexer** : `seo.allow_indexing: true`. C'est l'ouverture aux
  moteurs : robots, sitemap (qui se remplit alors), balises meta basculent
  ensemble. Recommandé : poser `seo.verification.google`/`bing` AVANT D2
  (prouver la propriété n'indexe rien et donne la visibilité console dès le
  premier crawl).

D1 et D2 sont deux commits distincts, revenables indépendamment.

## Porte E — Vérification post-publication (responsable : opérateur, dans l'heure)

- **E1 (après D1)** : sur l'origine réelle — `curl -sI https://monprojetsolaire.be/`
  → 200 ; meta robots encore `noindex` ; `/panneaux-solaires-sans-apport` →
  404 si A2+B non faits, 200 sinon ; aucun lien interne vers une page 404
  (le crawl outillé tourne aussi contre la production :
  `python tools/seo_precrawl.py --base https://monprojetsolaire.be ...`).
- **E2 (après D2)** : meta robots `index, follow` ; `robots.txt` n'interdit
  plus ; `sitemap.xml` liste les routes attendues (et la landing SEULEMENT si
  publiable) ; `/llms.txt` répond 200 ; soumission du sitemap en Search
  Console ; demande d'indexation de `/` et des pages piliers.
- **E3 (J+7)** : couverture Search Console (pages découvertes/indexées),
  aucune erreur de balisage structuré signalée, re-crawl outillé → 0 constat.

## Rollback

Chaque cran se referme par le geste inverse, isolément :

| Situation | Geste | Effet |
|---|---|---|
| Problème de contenu après D2 | `allow_indexing: false` (commit + déploiement) | noindex/robots/sitemap se referment ensemble ; demander la désindexation en console si besoin |
| Problème structurel après D1 | `staging: true` | bandeau et posture préproduction reviennent ; rien d'autre à toucher |
| Problème sur l'offre/la landing seulement | `offer.status: retired` (ou `pending_legal_review: true`) | la landing disparaît (404), sort du sitemap, ses liens entrants disparaissent — le reste du site ne bouge pas |
| Un fait d'offre périmé | `valid_until` dans le passé sur CE fait (nouvelle version + historique) | le fait se tait, la page repasse en formulation générique |

Le rollback ne réécrit jamais l'historique du registre : retirer une offre est
une nouvelle version avec l'ancienne dans `history`.

## Pile locale de pré-publication (référence)

```
export SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///<scratch>/qa.db"
export SEOLEAD_INTERNAL_API_KEY=<clé locale>
# (option simulation : export SEOLEAD_SITE_CONFIG_DIR=<copie des configs>)
.venv/bin/uvicorn app.main:app --port 8600 &
cd web && SEOLEAD_API_URL=http://127.0.0.1:8600 SEOLEAD_INTERNAL_KEY=<clé> \
  npm run build && npx next start -p 3100 &
```

Piège connu : le cache de fetch de Next (`web/.next/cache/fetch-cache`)
persiste entre redémarrages — le vider à chaque changement de configuration
servie, sous peine de crawler l'état d'avant.
