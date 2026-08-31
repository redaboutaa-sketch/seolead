# Cluster « financement / sans apport » — mot-clé → intention → page cible

**Règle anti-cannibalisation** : une intention transactionnelle (« je veux le
faire sans apport ») atterrit sur la **landing commerciale** ; une intention
informationnelle (« comment ça marche, combien, est-ce rentable ») atterrit sur
un **contenu éditorial** issu du pipeline, qui renvoie vers la landing. Deux
pages ne visent jamais la même intention — c'est la garde `DUPLICATE_TITLE`
au niveau éditorial, et cette table au niveau du plan.

Les seeds éditoriaux passent par le pipeline existant et toutes ses portes
(FINANCING_PROMISE classant HIGH/OFFICIAL, registre d'offre, substance N=8,
arbitrage). Un article de recherche ne peut PAS affirmer notre offre : il
explique le domaine et renvoie vers la landing pour l'offre.

| mot-clé | intention | page cible |
|---|---|---|
| panneaux solaires sans apport | transactionnelle | `/panneaux-solaires-sans-apport` |
| panneaux photovoltaïques sans apport | transactionnelle | `/panneaux-solaires-sans-apport` |
| panneaux solaires sans avancer d'argent | transactionnelle | `/panneaux-solaires-sans-apport` |
| installation photovoltaïque sans investissement initial | transactionnelle | `/panneaux-solaires-sans-apport` |
| installer panneaux solaires sans économies | transactionnelle | `/panneaux-solaires-sans-apport` |
| réduire facture électricité sans apport | transactionnelle | `/panneaux-solaires-sans-apport` |
| panneaux solaires petit budget | mixte → transactionnelle | `/panneaux-solaires-sans-apport` |
| financement panneaux solaires Belgique | informationnelle | éditorial (seed pipeline) → lien landing |
| panneaux solaires financement | informationnelle | éditorial (seed pipeline) → lien landing |
| mensualité panneaux solaires | informationnelle | éditorial (seed pipeline) → lien landing |
| panneaux solaires autofinancés | informationnelle (formulation à risque) | éditorial (seed pipeline) — le titre reformule : « une installation peut-elle s'autofinancer ? » |

## Commandes de seed (à lancer après la levée juridique, pas avant)

Un article de financement généré avant la levée serait bloqué par ses propres
portes (aucune source ne peut établir FINANCING_PROMISE) — le lancer avant
n'est pas dangereux, c'est du budget brûlé. Après la bascule :

```bash
docker exec seolead_api seolead research run --vertical SOLAR_BE \
  --query "financement panneaux solaires Belgique" --market BE --language fr
docker exec seolead_api seolead research run --vertical SOLAR_BE \
  --query "mensualité panneaux solaires Belgique" --market BE --language fr
```

## Questions AEO couvertes aujourd'hui

| question | où la réponse courte vit |
|---|---|
| Peut-on installer des panneaux solaires sans apport en Belgique ? | landing, DirectAnswer (≤ 50 mots) |
| Faut-il un apport pour installer des panneaux solaires ? | FAQ accueil + FAQ landing (schéma FAQPage) |
| Une installation peut-elle s'autofinancer ? | FAQ accueil + FAQ landing |
| Quels frais faut-il prévoir au départ ? | FAQ landing |
| Comment savoir si mon projet est éligible ? | FAQ landing |
| Combien faut-il avancer ? / Quelle mensualité ? | **sans réponse chiffrée tant que le registre d'offre n'est pas validé** — la page explique la méthode, jamais un faux chiffre |
