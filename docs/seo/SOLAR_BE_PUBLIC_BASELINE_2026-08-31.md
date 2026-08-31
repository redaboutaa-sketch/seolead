# SOLAR_BE — Baseline technique public — 2026-08-31 (jour du lancement)

Point zéro AVANT que Google produise des données. Chaque ligne vient d'une
mesure datée : la santé publique exécutée sur l'hôte à 20:10Z (VERDICT OK),
l'inspection Search Console du même jour, ou le code servi (indiqué). Les
colonnes que seule une console peut remplir restent vides — la règle
NO FAKE SEO DATA de l'ordre post-publication s'applique ici comme partout.

## État des URLs publiques (santé hôte 2026-08-31T20:10Z + GSC)

| URL | HTTP | robots (meta) | en-tête X-Robots-Tag | canonical | sitemap | Google | notes |
|---|---|---|---|---|---|---|---|
| `/` | 200 | index, follow | absent (mesuré après #39) | ✔ | ✔ | **indexée** — « Cette URL est sur Google », inspection GSC 2026-08-31 | |
| `/rentabilite-panneaux-solaires-belgique` | 200 | index, follow | absent | ✔ | ✔ | — | révision 2, OWNER APPROVED, publiée 2026-08-31 |
| `/outils/estimation-solaire` | 200 | index, follow | absent | ✔ | ✔ | — | |
| `/demande-etude` | 200 | index, follow | absent | ✔ | ✔ | — | |
| `/confidentialite` | 200 | index, follow | absent | ✔ | ✔ | — | |
| `/prix-panneaux-solaires-belgique` | 200 | **noindex** (figé soft-launch) | absent | ✔ | non (filtre noindex) | n/a — état voulu | CONTENT_REFRESH_CANDIDATE_1, intact jusqu'aux données GSC |
| `/conditions` | 200 | **noindex, nofollow, nocache** | absent | ✔ | non (SELF_NOINDEX_PATHS) | n/a — état voulu | texte légal en attente |
| `/panneaux-solaires-sans-apport` | **404** | n/a | n/a | n/a | non | n/a | EXPECTED_GATED_404 — pending_legal_review, jamais un incident |
| `/robots.txt` | 200 | — | — | — | — | — | allow, Disallow /preview/ et /api/ |
| `/sitemap.xml` | 200 | — | — | — | — | — | 5 `<loc>` exactement (liste ci-dessus) ; jamais la landing financement |
| `/llms.txt` | 200 | — | — | — | — | — | |
| `/preview/*` | 401 basicauth (edge Traefik) | n/a | n/a (jamais servi sans auth ; en-tête posé par le middleware une fois authentifié) | n/a | non | n/a | fermé deux fois |

Vérifications console du jour : propriété Search Console **URL-prefix**
vérifiée (balise `google-site-verification`, servie) ; jeton **Bing**
`msvalidate.01` servi en production (PR #40) — clic « Vérifier » côté
propriétaire. Le quota quotidien GSC de demandes manuelles a été consommé
par les trois tentatives refusées d'avant le correctif ; les demandes pour
les trois URLs restantes passent au prochain jour de quota.

## Signal d'indexation — architecture au point zéro

Depuis les PRs #39/#41 (2026-08-31) : la **meta robots par page** (dérivée
de la config, fail-closed) est l'unique autorité pour les routes publiques ;
`robots.txt` et le sitemap répondent à la même config ; l'en-tête
`X-Robots-Tag` n'existe que sur `/preview` et `/api` (middleware Next,
inconditionnel). L'historique des trois refus d'indexation et leur cause
est journalisé dans `SOLAR_BE_INDEXATION_TRACKING.md`.

## Données structurées (d'après le code servi — `web/lib/jsonld.ts`)

Types émis par le site : `Organization` (Beaver Data Group, opérateur),
`WebSite`, `WebPage`, `Article`, `FAQPage`/`Question`/`Answer`, `Service`,
`Place`/`Country`/`PostalAddress`. Composition constatée dans le code : la
page d'accueil émet `graph(organizationNode, websiteNode, faqNode)`
(`web/app/page.tsx:15`). Le crawl conteneur du 2026-08-31 a validé le
JSON-LD servi : **0 constat** (aucun JSON-LD invalide). Le relevé
type-par-route exhaustif se fait au prochain crawl — ne pas le déduire.

## Carte de maillage interne (d'après le code servi, 2026-08-31)

Chaîne de conversion visée : requête informationnelle → contenu utile →
estimation → demande d'étude.

| Source | Ancre | Destination | Intention |
|---|---|---|---|
| Header (toutes pages) | « Accueil » | `/` | navigation |
| Header | « Prix » | `/prix-panneaux-solaires-belgique` | commerciale (page noindex mais servie — le lien reste légitime pour les visiteurs) |
| Header | « Rentabilité » | `/rentabilite-panneaux-solaires-belgique` | informationnelle → commerciale |
| Header | « Estimation » | `/outils/estimation-solaire` | transactionnelle (outil) |
| Header | « Demander une étude » | `/demande-etude` | conversion |
| Hero accueil, CTA primaire | (data-cta="primary") | `/demande-etude` | conversion |
| Hero accueil, CTA secondaire | — | `/outils/estimation-solaire` | transactionnelle |
| Hero accueil, mention financement | « Découvrir les solutions sans apport » | `/panneaux-solaires-sans-apport` | **masquée** — conditionnée à `financingLandingVisible(config)`, faux tant que l'offre n'est pas publiable |
| FAQ accueil, liens de réponse | variables | routes connues uniquement (`isKnownRoute`), landing financement même garde | informationnelle |
| Accueil, section pages publiées | titre de l'article | `/rentabilite-panneaux-solaires-belgique` | informationnelle |
| Footer (toutes pages) | « Confidentialité » / « Conditions » | `/confidentialite`, `/conditions` | légale |

Règle de l'ordre : **ne modifier ce maillage que si une faiblesse réelle
apparaît dans les données.** Aucune sur-optimisation d'ancres. Le seul point
à surveiller quand les données GSC arrivent : l'ancre « Prix » pointe vers
une page noindex — si les requêtes prix génèrent des impressions, c'est le
déclencheur documenté du refresh (CONTENT_REFRESH_CANDIDATE_1), pas un
changement d'ancre.

## Prix vs rentabilité — intentions distinctes (rappel de l'ordre)

`/rentabilite-…` (canonique actuel) porte : rentabilité, ROI,
amortissement. `/prix-…` (futur canonique après refresh déclenché par les
données) portera : prix, coût, prix avec batterie. **Pas de fusion, pas de
redirection** sans données GSC démontrant une cannibalisation réelle.

## Audit ciblé `/conditions` — checklist préparée (chantier non bloquant)

Périmètre STRICT (ordre post-publication) — vérifier que le texte actuel
couvre, sans qualification juridique nouvelle et sans ouvrir l'indexation :

- [ ] identité de l'exploitant : Beaver Data Group (n° 935097675), rôle exact
- [ ] rôle de « Mon Projet Solaire » : marque/service, pas d'entité distincte
- [ ] collecte de leads : quelles données, quelle finalité
- [ ] rendez-vous : ce que « intérêt pour un rendez-vous » engage (rien de plus)
- [ ] transmission SG Solution : conditionnelle, jamais présentée comme automatique
- [ ] terminologie de consentement : alignée sur les cases versionnées réelles du formulaire
- [ ] coordonnées de contact : celles de la config (jamais d'autres)

## Prochaine décision de contenu

`WAIT_FOR_DATA` — aucune donnée Search Console de requêtes/impressions
n'existe encore. Les déclencheurs du refresh prix sont documentés ci-dessus
et dans l'ordre post-publication ; la mesure GEO J+7 est planifiée au
2026-09-07 (protocole `SOLAR_BE_GEO_BASELINE.md`, résultats jamais
fabriqués).
