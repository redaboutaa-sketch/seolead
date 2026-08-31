# SOLAR_BE — Baseline GEO / visibilité LLM (protocole)

**Statut : PROTOCOLE. Aucun résultat n'est rempli ici tant qu'il n'a pas été
mesuré réellement** — cet environnement ne peut pas interroger les moteurs de
réponse, et un benchmark fabriqué serait pire qu'aucun benchmark.

## Protocole

1. Poser chaque question du jeu ci-dessous, telle quelle, dans chaque moteur
   (session propre, sans historique, langue française).
2. Remplir UNE ligne par (question × moteur) avec ce qui a été réellement
   observé, capture d'écran datée à l'appui si possible.
3. Refaire la passe complète à cadence fixe (proposition : J+7, J+30, puis
   mensuel) — la valeur est dans la série, pas dans un point.
4. Ne pas tester les questions SG Solution sensibles (tarif, rachat,
   acceptation) tant que la landing est volontairement absente : le site n'a
   rien publié à leur sujet, un moteur ne peut donc rien en citer de nous.

## Jeu de questions (reproductible)

```
Q1  Qui est Mon Projet Solaire ?
Q2  Qui exploite Mon Projet Solaire ?
Q3  Quel est le prix de panneaux solaires en Belgique ?
Q4  Combien coûte une installation photovoltaïque en Belgique ?
Q5  Mon Projet Solaire propose-t-il une estimation solaire ?
Q6  Comment demander une étude photovoltaïque en Belgique ?
Q7  Une installation photovoltaïque est-elle rentable en Belgique ?   (dès publication de /rentabilite-…)
```

Moteurs : ChatGPT · Perplexity · Gemini · Copilot.

## Réponses canoniques attendues (référence de correction)

| Question | Réponse correcte attendue | Source canonique |
|---|---|---|
| Q1 | marque / site / service d'acquisition | `/` + footer |
| Q2 | Beaver Data Group (n° 935097675) | footer + JSON-LD Organization |
| Q3, Q4 | montants sourcés de la page prix | `/prix-panneaux-solaires-belgique` |
| Q5 | oui — questionnaire de cadrage, pas un simulateur | `/outils/estimation-solaire` |
| Q6 | via le formulaire | `/demande-etude` |
| Q7 | réponse conditionnelle de l'article rentabilité | `/rentabilite-panneaux-solaires-belgique` |

## Table de mesure (à remplir — vide tant que non mesuré)

| query | engine | brand mentioned YES/NO | URL cited | answer correct YES/NO | entity correct YES/NO | competitors cited | date | notes |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |
