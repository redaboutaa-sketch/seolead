# SOLAR_BE — Mesure J+8 (2026-09-08) : acquisition et Search Console

Première mesure portant sur des données Google réelles. Deux sources, toutes
deux datées : l'export Search Console « Performances sur les résultats de
recherche » du 2026-09-08 (7 derniers jours, type Web), et `seolead leads
report` / `leads list` exécutés sur l'hôte le 2026-09-08.

## 1. Correction du rapport du Lot A

**Le rapport du Lot A du 2026-09-03 affirmait un lead réel. C'est faux.**

Il annonçait « un seul lead réel depuis le 31/08 : `23bb534a` », en écartant
`6b062901` comme soumission de test du propriétaire. La mesure du 2026-09-08
montre que les deux soumissions partagent la même adresse masquée, le même
code postal, la même page d'atterrissage, le même canal `direct`, le même
jour. Le propriétaire a confirmé le 2026-09-08 que `23bb534a` est également
sa propre soumission.

| Identifiant | Créé | Nature réelle | État |
|---|---|---|---|
| `6b062901` | 2026-08-31 09:14Z | soumission de test du propriétaire | PENDING_EXPORT |
| `23bb534a` | 2026-08-31 17:05Z | soumission de test du propriétaire | PENDING_EXPORT |

**Nombre de leads réels depuis le lancement : zéro.**

Ce que l'erreur enseigne : deux enregistrements distincts en base ne font pas
deux personnes distinctes. Le rapport avait traité « identifiant différent »
comme « lead différent », alors que les attributs disponibles sans consulter
la PII — adresse masquée, code postal, canal, jour — disaient déjà le
contraire. Une mesure qui compte des lignes n'est pas une mesure qui compte
des gens.

Conséquences opérationnelles :

- Les DEUX leads sont à archiver (`seolead leads archive <id> --by … --reason
  … --apply`), pas seulement `6b062901`.
- Il n'existe aucun lead réel à exporter. Après le geste 5, la seconde
  soumission de bout en bout sera le premier et le seul dépôt réel.
- Aucun lead n'est jamais venu d'une recherche : les deux portent
  `channel: direct`, `source: null`, `search_intent: null`.

## 2. Search Console — 7 jours (2026-08-31 → 2026-09-06)

Google publie avec environ deux jours de retard ; la fenêtre s'arrête donc au
2026-09-06.

| Total | Valeur |
|---|---|
| Clics | **0** |
| Impressions | **70** |
| CTR | 0 % |
| Position moyenne | **66** |

Les tableaux par dimension ne totalisent pas identiquement (70 par jour, par
pays et par appareil ; 74 par page ; 68 par requête) : Google agrège chaque
dimension séparément et exclut les requêtes anonymisées. Les écarts sont
reportés tels quels, pas lissés.

### Par jour

| Date | Impressions | Position |
|---|---|---|
| 2026-08-31 | 0 | — |
| 2026-09-01 | 4 | 70,0 |
| 2026-09-02 | 16 | 56,7 |
| 2026-09-03 | 15 | 66,7 |
| 2026-09-04 | 13 | 64,8 |
| 2026-09-05 | 10 | 65,4 |
| 2026-09-06 | 12 | 69,2 |

### Par page

| URL | Impressions | Position |
|---|---|---|
| `/` | 43 | 47,1 |
| `/rentabilite-panneaux-solaires-belgique` | 28 | 89,0 |
| `/confidentialite` | 1 | 2,0 |
| `/demande-etude` | 1 | 3,0 |
| `/outils/estimation-solaire` | 1 | 4,0 |

### Par requête

| Requête | Impressions | Position |
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

Pays : Belgique 68, France 1, Maroc 1. Appareils : ordinateur 62 (position
60,8), mobile 8 (position 93,0).

## 3. Ce que ces chiffres établissent

**Cinq URLs sont indexées, pas une.** Une page ne peut pas recevoir
d'impression sans être indexée : `/`, `/rentabilite-…`, `/confidentialite`,
`/demande-etude` et `/outils/estimation-solaire` sont donc toutes connues de
Google. Le suivi d'indexation ne confirmait que `/` sur inspection manuelle.

**Le ciblage sémantique fonctionne, le classement non.** L'article
rentabilité est mis en face de « rentabilité panneaux solaires wallonie » et
« rendement panneau solaire belgique » : ce sont exactement ses requêtes
cibles. Il y apparaît en position 88 à 98, soit page 9 ou 10. La page
d'accueil apparaît en position 42 à 60 sur des requêtes contenant « projet »,
qui font écho au nom de marque.

**Zéro clic n'est pas une anomalie, c'est de l'arithmétique.** À une position
moyenne de 66, le taux de clic attendu est nul. Il n'y a rien à corriger dans
les titres ou les métas tant que les positions restent au-delà de la
deuxième page : personne ne voit ces résultats.

**Le cluster commercial est absent de la mesure.** Aucune requête contenant
« prix » ou « coût » n'apparaît, alors que ce sont les requêtes à intention
d'achat. La cause est connue et voulue :
`/prix-panneaux-solaires-belgique` porte un `noindex` figé au soft-launch.
La page la plus proche d'un lead est la seule que Google a interdiction de
montrer.

**Le mobile est deux fois moins bien classé que l'ordinateur** (93 contre
60,8), sur 8 impressions seulement. Échantillon trop petit pour conclure ;
à revoir à J+30.

## 4. Ce que ces chiffres n'établissent pas

- Aucune tendance. Six jours de données, sur un domaine de huit jours.
- Aucune information sur les concurrents ni sur la difficulté réelle des
  requêtes : DataForSEO est à court de crédits depuis le 2026-09-02.
- Aucune donnée GEO. La grille J+7 (`SOLAR_BE_GEO_J7_2026-09-07.md`) est
  toujours vide.
