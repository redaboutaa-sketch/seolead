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
| `https://monprojetsolaire.be/prix-panneaux-solaires-belgique` | 200 | ✔ | **index, follow** (depuis le 2026-09-10) | ✔ (sitemap à 6 URLs) | — *demande d'indexation à faire* | — | 2026-09-10 |
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
- **2026-09-10** — la page prix devient indexable. Publiée en soft-launch le
  13 août avec un `noindex` gelé dans son instantané, elle est restée
  invisible six semaines : sur les 100 impressions mesurées jusqu'au 8
  septembre, aucune requête contenant « prix ». Republiée en v2 puis v3,
  elle sert désormais `index, follow`. Sitemap resoumis, 6 URLs.
  **Reste à faire : demander l'indexation de cette URL dans Search Console** —
  les quatre demandes du 2026-09-10 portaient sur les autres pages, à un
  moment où celle-ci était encore `noindex`.

  Trois défauts ont été trouvés en chemin, tous corrigés :
  1. *l'impasse d'approbation* — la porte refusait de republier une page dont
     l'approbation ne nommait aucun rendu, et prescrivait « ré-approuver avec
     --fingerprint », remède inatteignable puisque `APPROVED` était terminal
     (PR #65) ;
  2. *l'ordre des écritures* — l'ancienne et la nouvelle ligne devenaient
     vivantes dans le même flush, et SQLAlchemy ordonne par clé primaire :
     une publication sur deux mourait sur `uq_pub_live`. L'index n'existait
     que dans la migration, donc aucun test ne pouvait le voir (PR #66) ;
  3. *deux montants faux* — « 1,2 € » lu comme 12, et « entre 6.000 et
     10.000 € » réduit à sa borne haute. En ligne depuis le 13 août, retirés
     ou corrigés dans la v3 (PR #67).

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
| 30/08–08/09 | `/` | 61 | 0 | 0 % | 49,0 | ✔ | 0 |
| 30/08–08/09 | `/rentabilite-…` | 40 | 0 | 0 % | 79,1 | ✔ | 0 |
| 30/08–08/09 | `/confidentialite` | 1 | 0 | 0 % | 2,0 | ✔ | 0 |
| 30/08–08/09 | `/demande-etude` | 1 | 0 | 0 % | 3,0 | ✔ | 0 |
| 30/08–08/09 | `/outils/estimation-solaire` | 1 | 0 | 0 % | 4,0 | ✔ | 0 |
| 30/08–08/09 | **tous** | **100** | **0** | **0 %** | **62,7** | — | **0** |
| 30/08–10/09 | `/` | 75 | 0 | 0 % | 48,7 | ✔ | 0 |
| 30/08–10/09 | `/rentabilite-…` | 52 | 0 | 0 % | 74,6 | ✔ | 0 |
| 30/08–10/09 | `/confidentialite` | 1 | 0 | 0 % | 2,0 | ✔ | 0 |
| 30/08–10/09 | `/demande-etude` | 1 | 0 | 0 % | 3,0 | ✔ | 0 |
| 30/08–10/09 | `/outils/estimation-solaire` | 1 | 0 | 0 % | 4,0 | ✔ | 0 |
| 30/08–10/09 | **tous** | **126** | **0** | **0 %** | **59,7** | — | **0** |

### Export du 2026-09-12 (fenêtre 30/08–10/09)

Position moyenne globale recalculée par pondération des impressions : 59,73
par appareil et 59,73 par pays, les deux dimensions concordent. Google ne
publie pas ce total ; les tableaux par dimension ne se recoupent pas
exactement (126 par jour, par pays et par appareil ; 130 par page ; 124 par
requête), et les écarts sont reportés tels quels.

Trois mesures successives sur le même site :

| fenêtre | impressions | clics | position |
|---|---|---|---|
| 31/08–06/09 | 70 | 0 | 66,0 |
| 30/08–08/09 | 100 | 0 | 62,7 |
| 30/08–10/09 | 126 | 0 | 59,7 |

La progression est régulière et antérieure à tout ce qui a été fait le 10
septembre : elle court du 1er au 10 et ne doit donc rien au `noindex` levé
ce jour-là à 18:44. C'est la maturation ordinaire d'un domaine neuf, pas un
effet de nos correctifs.

L'article rentabilité progresse le plus vite : position 89,0 puis 79,1 puis
74,6, pour 28 puis 40 puis 52 impressions. Il est servi sur ses requêtes
cibles ; il lui manque l'autorité, pas la pertinence.

Toujours neuf requêtes, les mêmes, et **toujours aucune contenant « prix »**.
La page prix n'apparaît pas non plus dans le tableau par page : elle n'est
devenue indexable que le 10 septembre à 18:44, soit le dernier jour de la
fenêtre, et Google ne l'avait jamais explorée (inspection GSC : « Sans
objet » partout). Cet export ne peut donc rien dire de son effet. La
première mesure qui le pourra est celle de J+30.

Le mobile reste derrière l'ordinateur pour la deuxième fenêtre consécutive
(16 impressions en position 70,2 contre 110 en position 58,2 ; précédemment
8 en 93,0 contre 62 en 60,8). L'écart se resserre et l'échantillon reste
trop petit pour conclure — à revoir à J+30 avant d'en faire une hypothèse.

La fenêtre du 2026-09-10 (28 jours, données à partir du 31/08) prolonge la
précédente : 100 impressions, toujours zéro clic, position moyenne en
amélioration de 66 à 62,7. Les deux derniers jours mesurés sont les meilleurs
(55,8 puis 53,2) et l'article rentabilité passe de 89,0 à 79,1 — dix jours de
données ne font pas une tendance, et ces positions restent hors de portée d'un
clic. La page prix n'y figure toujours pas : elle n'est devenue indexable que
le 10 septembre.

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
