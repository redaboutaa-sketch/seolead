# SOLAR_BE — Crawl SEO de pré-publication (RC1, 2026-08-31)

Produit par `tools/seo_precrawl.py` sur la pile locale de pré-publication
(build de production Next + API sur SQLite, voir le runbook). Deux passes :
la configuration réelle du dépôt, puis la simulation de publication via
`SEOLEAD_SITE_CONFIG_DIR` (copie avec `staging: false`, `allow_indexing`
inchangé à `false` — rien n'est devenu indexable nulle part).

### Crawl — staging (config réelle du dépôt : staging=true, allow_indexing=false)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, Question, WebSite | ✓ | 6 | 6340 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 668 c |
| `/confidentialite` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 5 | 5329 c |
| `/demande-etude` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 1409 c |
| `/llms.txt` | 404 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 9 o |
| `/outils/estimation-solaire` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1502 c |
| `/panneaux-solaires-sans-apport` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/panneaux-solaires-sans-apport | Installer des panneaux solaires sans apport en Bel | ✓ | 1 | Answer, Country, FAQPage, Organization, Question, Service, WebPage, WebSite | ✓ | 6 | 7357 c |
| `/prix-panneaux-solaires-belgique` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 27 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 110 o |

**Constats (0)**

- aucun

### Crawl — simulation publication (staging→false via SEOLEAD_SITE_CONFIG_DIR ; allow_indexing=false inchangé)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, Question, WebSite | ✓ | 5 | 6110 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 668 c |
| `/confidentialite` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 5 | 5329 c |
| `/demande-etude` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 1409 c |
| `/llms.txt` | 404 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 9 o |
| `/outils/estimation-solaire` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 1352 c |
| `/panneaux-solaires-sans-apport` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/prix-panneaux-solaires-belgique` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 27 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 110 o |

**Constats (0)**

- aucun

## Corrections appliquées entre les deux passes

La première passe de simulation avait 1 constat, la première passe staging 3 ;
tous corrigés dans cette RC (les tables ci-dessus sont l'état APRÈS) :

1. **Lien cassé au jour J** : le hero et la FAQ de l'accueil liaient la
   landing financement pendant qu'elle-même, correctement, répond 404 en
   production tant que l'offre n'est pas publiable. La porte de visibilité
   (`financingLandingVisible`) est désormais partagée entre la page et tout
   ce qui pointe vers elle.
2. **Canonicals** : seule la landing en portait un ; toutes les pages HTML en
   émettent un désormais, résolu contre l'origine configurée.
3. **Meta descriptions dupliquées** : `/conditions` et `/confidentialite`
   retombaient sur la description par défaut ; chacune décrit sa page.
4. **Robots incohérents à terme** : `/demande-etude` et
   `/outils/estimation-solaire` sont dans la table de routes (donc dans le
   sitemap le jour de l'indexation) mais portaient un noindex codé en dur ;
   ils suivent la porte du site.

## Revue de la landing financement (quatre angles)

**SEO.** Title exact-match sur la requête cible, H1 unique, réponse directe
≤ 50 mots en tête, FAQ balisée, canonical, OG, 7 357 caractères servis sans
JavaScript, maillage entrant (hero + FAQ accueil) et sortant (formulaire).
Reste ouvert : la page n'a pas de fil d'Ariane (acceptable à une profondeur
de 1), et son indexabilité est correctement suspendue au registre.

**AEO.** La réponse directe et chaque entrée FAQ sont autoportantes (citables
hors contexte) et au conditionnel. Le JSON-LD reflète exactement le texte
visible — rien dans le balisage qui ne soit pas sur la page.

**Conversion.** CTA primaire au-dessus du pli, répété en fin de page ;
la promesse du CTA (« Vérifier mon projet ») est cohérente avec ce que le
formulaire fait ; l'étude est dite « sans engagement » et gratuite aux deux
endroits où la question se pose. Point d'attention (non bloquant, mesurable
après publication) : la page assume de ne montrer AUCUN chiffre — c'est la
politique d'affirmations ; si le taux de conversion en souffre, la réponse
est le `worked_example` validé du registre, pas un chiffre générique.

**Conformité.** Toutes les formulations financement sont au conditionnel avec
les frais annoncés avant engagement ; l'inventaire verbatim L-1…L-16 est dans
`docs/legal/SOLAR_BE_FINANCING_REVIEW.md` et AUCUNE de ces formulations n'est
présumée conforme ici : la page reste non-publiable tant que la matrice de
verdicts n'est pas remplie. Le bloc `mandatory_disclosures` est en place et
vide — il rendra les mentions du juriste telles quelles.
