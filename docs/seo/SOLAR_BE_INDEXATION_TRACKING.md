# SOLAR_BE — Suivi d'indexation et mesure SEO

Règle du document : **une case vide reste vide jusqu'à la donnée réelle.**
« Crawlable » vient de `tools/public_health_check.sh` / `tools/seo_precrawl.py` ;
« indexed » ne vient QUE de Search Console / Bing — jamais déduit de
« crawlable ». Les cinq états sont distincts :

```
crawlable → discovered → crawled → indexed → ranking
```

## Jeu d'URLs canonique

| URL | HTTP | canonical | meta robots | sitemap | Google indexed | Bing indexed | last checked |
|---|---|---|---|---|---|---|---|
| `https://monprojetsolaire.be/` | 200 | ✔ | index, follow | ✔ | — | — | 2026-08-31 (crawl) |
| `https://monprojetsolaire.be/prix-panneaux-solaires-belgique` | 200 | ✔ | noindex (figé soft-launch — voir post-publication) | retirée au prochain déploiement | — | — | 2026-08-31 |
| `https://monprojetsolaire.be/rentabilite-panneaux-solaires-belgique` | — (publish restant) | — | — | dès publication | — | — | — |
| `https://monprojetsolaire.be/outils/estimation-solaire` | 200 | ✔ | index, follow | ✔ | — | — | 2026-08-31 |
| `https://monprojetsolaire.be/demande-etude` | 200 | ✔ | index, follow | ✔ | — | — | 2026-08-31 |

Priorité de demande d'indexation (dès Search Console configurée, jamais un
draft, jamais un 404 volontaire, jamais une non-canonique) :
1. `/` · 2. `/prix-…` (une fois ré-indexable) ou `/rentabilite-…` (une fois
publiée) · 3. `/outils/estimation-solaire` · 4. `/demande-etude`.

## Hebdomadaire (modèle — valeurs UNIQUEMENT depuis Search Console)

| semaine | URL | impressions | clicks | CTR | position moyenne | indexed | leads |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Cluster de requêtes initial (hypothèse, à remplacer par les requêtes réelles GSC)

prix panneaux solaires Belgique · prix installation photovoltaïque Belgique ·
coût panneaux solaires Belgique · combien coûtent les panneaux solaires ·
prix panneaux photovoltaïques · prix panneaux solaires avec batterie ·
rentabilité panneaux solaires Belgique.

Discipline contenu : **pas de génération en masse** — les 5 briefs
(RC1_GEO_LIENS_CONTENUS.md §3) attendent les premières données réelles
(requêtes, impressions, CTR, positions) pour éviter cannibalisation et
contenu sans demande.
