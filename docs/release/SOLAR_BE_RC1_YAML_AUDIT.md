# SOLAR_BE — Audit YAML repo-wide (RC1, 2026-08-31)

Question posée : le bug « `value: YES` → `True` » (trouvé dans
`battery_interest`, et présent dans une vraie qualification de lead en
production) était-il isolé ou systémique ?

## Méthode

1. Pathologie de référence, mesurée sur PyYAML par défaut (une ligne chacune) :

   | Écrit | Lu par YAML 1.1 | Classe |
   |---|---|---|
   | `YES` | `True` (bool) | booléens 1.1 |
   | `0123` | `83` (int, lecture octale) | zéro de tête |
   | `2026-08-31` | `datetime.date(2026, 8, 31)` | timestamp implicite |
   | `12:30` | `750` (int, lecture sexagésimale) | sexagésimal |
   | `Off` | `False` (bool) | booléens 1.1 |

2. Inventaire : chaque fichier YAML suivi par git, chaque scalaire, comparé
   entre le chargeur par défaut et le chargeur strict
   (`app/core/strict_yaml.py`), après réparation du cas `battery_interest`
   (valeurs de choix mises entre guillemets dans la PR #30).

## Résultat — table fichier par fichier

| Fichier | Clé | Brut | Lu (1.1) | Attendu | Action |
|---|---|---|---|---|---|
| `config/sites/solar_be.yaml` | `fields[].options[].value` (battery_interest : YES/MAYBE/NO) | `YES` etc. **avant réparation** | `True`/`False` | chaîne `"YES"` | **Réparé** (guillemets, PR #30) + garde pydantic + chargeur strict |
| `config/sites/solar_be.yaml` | tout le reste | — | aucune divergence | — | aucune |
| `config/sites/demo_generic.yaml` | — | — | aucune divergence | — | aucune |
| `config/verticals/solar_be.yaml` | — | — | aucune divergence | — | aucune |
| `config/verticals/test_generic.yaml` | — | — | aucune divergence | — | aucune |
| `docker-compose.yml` | — | — | aucune divergence | — | aucune |
| `infra/traefik/docker-compose.public.yml` | — | — | aucune divergence | — | aucune |

Diff de types chargeur par défaut ↔ chargeur strict, tous fichiers, état
RC1 : **0**. Jetons ambigus restants (YES/No/On/Off, zéros de tête, dates
nues, sexagésimaux) : **0**. Les booléens légitimes du dépôt sont tous
écrits `true`/`false` minuscules, la seule graphie que le chargeur strict
résout.

## Verdict

**Le bug YES était isolé** — une seule clé touchée, réparée — mais la CLASSE
ne l'était pas : rien n'empêchait la prochaine option `NO`, la prochaine
version `0123` ou le prochain horaire `12:30` de changer de type en silence.

## Garde structurelle (fermeture de la classe)

- `app/core/strict_yaml.py` : `StrictConfigLoader` vide tous les résolveurs
  implicites et ne réadmet que `true|false` minuscules, `null`, les entiers
  décimaux sans zéro de tête, les flottants simples. Tout le reste reste la
  chaîne écrite — dates comprises (les configs typent leurs dates en `str`
  à dessein ; `OfferFact` les parse ensuite bruyamment).
- Branché dans les DEUX chargeurs de configuration (`app/site/config.py`,
  `app/verticals/profile.py`). Les données de fournisseurs ne passent pas
  par lui : leurs schémas propres les valident.
- Seconde ligne : le validateur pydantic refuse toute valeur d'option
  booléenne dans `SiteConfig` (la forme exacte du bug d'origine).
- Régression épinglée : `tests/test_strict_yaml.py` mesure d'abord que le
  chargeur par défaut fait bien le mal documenté (le témoin), puis que le
  strict garde la chaîne ; 3 mutants sur les résolveurs, 3 tués.
