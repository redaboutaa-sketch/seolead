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
| `https://monprojetsolaire.be/` | 200 | ✔ | index, follow | ✔ | **✔ indexée** (inspection GSC 31/08, confirmée par 43 impressions) | — | 2026-09-08 |
| `https://monprojetsolaire.be/prix-panneaux-solaires-belgique` | 200 | ✔ | noindex (figé soft-launch — voir post-publication) | retirée (filtre noindex du sitemap) | n/a — état voulu | — | 2026-09-08 |
| `https://monprojetsolaire.be/rentabilite-panneaux-solaires-belgique` | 200 | ✔ | index, follow | ✔ | **✔ indexée** (28 impressions, position 89) | — | 2026-09-08 |
| `https://monprojetsolaire.be/outils/estimation-solaire` | 200 | ✔ | index, follow | ✔ | **✔ indexée** (1 impression, position 4) | — | 2026-09-08 |
| `https://monprojetsolaire.be/demande-etude` | 200 | ✔ | index, follow | ✔ | **✔ indexée** (1 impression, position 3) | — | 2026-09-08 |
| `https://monprojetsolaire.be/confidentialite` | 200 | ✔ | index, follow | ✔ | **✔ indexée** (1 impression, position 2) | — | 2026-09-08 |

Journal des faits d'indexation (constatés, jamais déduits) :

- **2026-08-31** — trois « Demande d'indexation refusée » successives sur
  `/demande-etude`, `/outils/estimation-solaire` et `/`. Cause réelle
  identifiée par le détail du test en direct GSC : « noindex détecté dans
  l'en-tête HTTP X-Robots-Tag » — l'en-tête contredisait la meta et Google
  suit le plus strict. Corrigé (PRs #39/#41 : une seule autorité, la meta
  pilotée par la config ; en-tête restreint à /preview et /api).
- **2026-09-08** — premier export Search Console (7 jours, 31/08 au 06/09) :
  70 impressions, **0 clic**, position moyenne 66. Cinq URLs reçoivent des
  impressions, ce qui prouve leur indexation sans inspection manuelle : une
  page non indexée ne peut pas être affichée. L'indexation n'est donc plus
  le goulot ; le classement l'est. Détail complet et analyse :
  `SOLAR_BE_MESURE_2026-09-08.md`.
- **2026-08-31, après déploiement du correctif** — inspection GSC de `/` :
  **« Cette URL est sur Google »**. Premier verdict d'indexation positif du
  site. Le quota quotidien de demandes manuelles était dépassé (consommé
  par les tentatives refusées) : les demandes pour les trois autres URLs
  passent au prochain jour de quota ; le sitemap soumis fait le même
  travail sans quota.

Priorité de demande d'indexation (dès Search Console configurée, jamais un
draft, jamais un 404 volontaire, jamais une non-canonique) :
1. `/` · 2. `/prix-…` (une fois ré-indexable) ou `/rentabilite-…` (une fois
publiée) · 3. `/outils/estimation-solaire` · 4. `/demande-etude`.

## Hebdomadaire (valeurs UNIQUEMENT depuis Search Console)

| semaine | URL | impressions | clicks | CTR | position moyenne | indexed | leads |
|---|---|---|---|---|---|---|---|
| 31/08–06/09 | `/` | 43 | 0 | 0 % | 47,1 | ✔ | 0 |
| 31/08–06/09 | `/rentabilite-…` | 28 | 0 | 0 % | 89,0 | ✔ | 0 |
| 31/08–06/09 | `/confidentialite` | 1 | 0 | 0 % | 2,0 | ✔ | 0 |
| 31/08–06/09 | `/demande-etude` | 1 | 0 | 0 % | 3,0 | ✔ | 0 |
| 31/08–06/09 | `/outils/estimation-solaire` | 1 | 0 | 0 % | 4,0 | ✔ | 0 |
| 31/08–06/09 | **tous** | **70** | **0** | **0 %** | **66** | — | **0** |

Leads : zéro lead réel depuis le lancement. Les deux soumissions en base sont
celles du propriétaire (voir `SOLAR_BE_MESURE_2026-09-08.md` §1).

## Requêtes réelles (GSC, 31/08–06/09) — remplacent l'hypothèse

Neuf requêtes produisent des impressions. Aucune ne contient « prix » ni
« coût » : le cluster commercial est absent parce que la page qui le vise
est `noindex`.

| requête | impressions | position |
|---|---|---|
| projet panneau solaire | 11 | 47,2 |
| projet photovoltaique | 11 | 59,9 |
| rentabilité panneaux solaires wallonie | 11 | 88,5 |
| projet de panneau solaire | 10 | 42,0 |
| projet panneaux photovoltaique | 9 | 47,0 |
| rentabilité panneaux solaires | 7 | 98,1 |
| rentabilité panneau solaire | 5 | 95,2 |
| rendement panneau solaire belgique | 3 | 92,0 |
| combien rapporte un panneau solaire | 1 | 75,0 |

L'hypothèse initiale visait juste sur l'intention (prix, rentabilité) et faux
sur le vocabulaire : les requêtes réellement servies contiennent « projet »,
écho du nom de marque, et « rendement » autant que « rentabilité ».

Discipline contenu : **pas de génération en masse** — les 5 briefs
(RC1_GEO_LIENS_CONTENUS.md §3) attendent les premières données réelles
(requêtes, impressions, CTR, positions) pour éviter cannibalisation et
contenu sans demande.
