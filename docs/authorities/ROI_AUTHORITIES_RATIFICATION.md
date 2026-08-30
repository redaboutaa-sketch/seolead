# Autorités du ROI — liste soumise à ratification

**Statut : proposition. Rien n'est actif.** Les deux entrées ajoutées à
`config/verticals/solar_be.yaml` portent `pending_ratification: true` et sont
exclues de tout registre que le pipeline consulte. Ratifier, c'est retirer ce
drapeau — un geste explicite, une ligne par entrée.

Le registre est une porte de confiance : y figurer autorise un domaine à établir
des affirmations à risque HIGH. Qui y entre relève de la personne responsable de
ce que le site publie, pas de qui a édité le fichier en dernier.

---

## 1. Le problème, mesuré

Une affirmation de rentabilité de portée belge est **arithmétiquement
insatisfiable** aujourd'hui.

```
ROI exige : autorité=INSTITUTIONAL  fraîcheur=REQUIRED  sources concordantes=2

Domaines qui parlent pour ROI :
  energie.wallonie.be   GOUVERNEMENT     région=BE-WAL   priorité=95
  energiesparen.be      AGENCE PUBLIQUE  région=BE-VLG   priorité=95
  apere.org             PROGRAMME OFF.   région=BE       priorité=60

Domaines dont la région couvre BE : 1   (apere.org)
Sources concordantes exigées      : 2
=> satisfiable : NON
```

La règle de portée régionale refuse — à juste titre — qu'une source wallonne
établisse une affirmation belge. Il faut donc **deux** sources nationales, et le
registre n'en contient qu'une. Aucune qualité de page ne peut compenser cela :
c'est un compte, pas un jugement.

Même situation pour Bruxelles : un seul domaine couvre BE-BRU. Wallonie et
Flandre sont à deux, donc satisfiables.

**Effet observé :** 17 affirmations à risque HIGH de catégorie ROI, toutes non
étayées, dans un article dont le sujet *est* la rentabilité.

---

## 2. Deux faits à connaître avant de ratifier

### 2.1 Le registre ne sait exprimer qu'un seul niveau de confiance

```
GOVERNMENT | REGULATOR | GRID_OPERATOR | PUBLIC_AGENCY | OFFICIAL_PROGRAM
        -> tous : SourceQuality.OFFICIAL, rang 5
```

Il n'existe aucun moyen d'inscrire un organisme comme `INSTITUTIONAL` (rang 4)
ou `SPECIALIST` (rang 3). **Tout ce qui entre au registre devient officiel.**

Conséquence déjà présente, et non introduite par cette proposition :
`apere.org` — une association de promotion des énergies renouvelables — porte
aujourd'hui exactement le même rang de confiance que la CREG, régulateur
fédéral. C'est votre unique autorité nationale du ROI.

C'est pourquoi cette proposition **exclut délibérément** les organismes de
recherche et les consortiums (EnergyVille, VITO, universités) : les inscrire les
promouvrait au rang officiel, ce qui serait faux. Ils redeviendront candidats le
jour où le registre saura dire « institutionnel ».

### 2.2 Je n'ai pas pu vérifier ces domaines sur pièces

L'egress réseau de l'environnement de travail est bloqué vers `apere.org`,
`energyville.be` et leurs pairs. Je peux affirmer ce que sont ces organismes ;
je **ne peux pas** affirmer qu'ils publient des chiffres de temps de retour pour
une installation résidentielle.

Proposer une porte de confiance sur ma seule mémoire serait exactement le
raisonnement que le reste de ce pipeline existe pour refuser. La sonde du § 4
est là pour que la question soit tranchée sur pièces.

---

## 3. Les entrées proposées

### 3.1 Nouvelles inscriptions — ajoutées, inactives

| domaine | organisme | type | région | catégories proposées |
|---|---|---|---|---|
| `plan.be` | Bureau fédéral du Plan | GOVERNMENT | BE | ROI, ENERGY_PRICE, MARKET_AVERAGE |
| `statbel.fgov.be` | Statbel — office belge de statistique | PUBLIC_AGENCY | BE | ENERGY_PRICE, MARKET_AVERAGE |

**`plan.be` — Bureau fédéral du Plan.** Organisme public fédéral d'analyse
économique, produit les perspectives énergétiques de la Belgique. Son autorité
sur l'économie de l'énergie au niveau national ne fait pas de doute. *Réserve :*
ses publications sont macroéconomiques ; qu'il descende jusqu'au temps de retour
d'une installation résidentielle est à établir par la sonde.

**`statbel.fgov.be` — Statbel.** Office statistique belge, autorité incontestée
sur les prix de l'électricité aux ménages — l'entrée dominante de tout calcul de
rentabilité. Volontairement **pas** proposé pour ROI : Statbel publie des prix,
pas des temps de retour. L'inscrire pour ENERGY_PRICE et MARKET_AVERAGE renforce
les affirmations de prix sans lui prêter une compétence qu'il n'a pas.

### 3.2 Élargissements proposés — non appliqués

Ces deux domaines sont **déjà** au registre et déjà ratifiés comme autorités
fédérales. Il ne s'agit pas d'accorder une confiance nouvelle, seulement
d'étendre ce sur quoi elle porte. Le geste est d'une ligne :

```yaml
    - domain: economie.fgov.be
      name: SPF Économie
      claim_categories: [TAX, REGULATION, ENERGY_PRICE, ROI, MARKET_AVERAGE]
      #                                               ^^^^^^^^^^^^^^^^^^^^ ajout
```

**Justification.** Le SPF Économie porte la Direction générale de l'Énergie et
publie l'information énergétique destinée aux consommateurs, coût des
installations compris. C'est l'ajout dont je suis le plus confiant.

```yaml
    - domain: creg.be
      name: CREG — régulateur fédéral de l'énergie
      claim_categories: [ENERGY_PRICE, TARIFF, REGULATION, ROI]
      #                                                    ^^^ ajout
```

**Justification et réserve.** La rentabilité d'une installation solaire belge
est déterminée d'abord par le prix de l'électricité évitée, et la CREG est
l'autorité fédérale sur ce prix. Mais sa compétence est le **prix**, pas le
**temps de retour**. Lui accorder ROI signifie qu'une page de la CREG sur les
composantes tarifaires pourrait venir étayer une affirmation d'amortissement.
C'est le plus discutable des quatre, et je le signale plutôt que de le glisser.

---

## 4. Comment ratifier sur pièces plutôt que sur parole

```bash
# Ce que les candidats retournent réellement à la question ROI
docker compose exec seolead_api seolead authority probe \
  --category ROI --include-pending

# Ce que les deux domaines déjà ratifiés retourneraient si on leur ouvrait ROI
docker compose exec seolead_api seolead authority probe \
  --category ROI --domain creg.be --domain economie.fgov.be
```

Lecture seule : aucun paquet écrit, aucun registre modifié, un candidat marqué
`pending_ratification` reste inactif dans le pipeline quoi qu'il arrive.

**Le critère de décision** est dans la sortie : pour chaque domaine, ce qu'il
retourne. Un domaine qui ne ramène que des pages de procédure administrative
n'établira jamais un temps de retour, et l'inscrire ne ferait que gonfler le
compte de sources sans rien étayer — le pire des résultats, parce qu'il
produirait des affirmations *apparemment* corroborées.

### Ratifier

Retirer la ligne `pending_ratification: true` de l'entrée retenue, et ajouter
les catégories des élargissements retenus. Rien d'autre.

---

## 5. L'option que vous devriez peser d'abord

Il se peut qu'aucun organisme national belge ne publie de temps de retour pour
une installation résidentielle — et que la sonde le montre. Ce ne serait pas un
échec : ce serait la découverte que **la rentabilité solaire en Belgique n'est
pas une grandeur nationale.** Le tarif prosumer, les certificats verts, les
primes et la compensation diffèrent par région ; c'est la Wallonie, la Flandre
et Bruxelles qui publient des chiffres de rentabilité, parce que ce sont elles
qui en fixent les termes.

Si c'est le cas, ajouter des domaines fédéraux ne réglera rien, et la vraie
question devient une décision de politique qui vous appartient :

> **Deux sources régionales de régions différentes, concordantes, peuvent-elles
> établir une affirmation de rentabilité de portée belge ?**

Aujourd'hui la réponse est non : la règle exige qu'une source couvre la portée
de l'affirmation, et BE-WAL ne couvre pas BE. C'est correct pour une prime — une
prime wallonne n'est pas une prime belge, et le prétendre serait faux. Ce l'est
moins pour un temps de retour, où l'accord entre la Wallonie et la Flandre est
précisément ce qui rend une affirmation belge crédible.

Je ne touche pas à cette règle : c'est la garde qui empêche un article
d'annoncer une prime régionale comme nationale, et l'assouplir au mauvais
endroit ferait exactement le dégât qu'elle prévient. Mais la question mérite
d'être posée avant d'ajouter des domaines pour contourner un problème qui n'est
peut-être pas là où on le cherche.

---

## 6. Effet attendu, et comment le vérifier

Après ratification, l'effet se mesure sans dépenser un appel de rédaction :

```bash
docker compose exec seolead_api seolead package replay <package_id>
```

La commande rejoue l'étiquetage des affirmations scellées sous la politique
courante. Elle **ne peut pas** recalculer le statut de preuve — cela demande le
corpus complet des passages, qui n'est pas conservé — donc le compte réel des 17
affirmations ROI re-jugées viendra d'une exécution complète du pipeline.

| indicateur | avant | après ratification |
|---|---|---|
| domaines ROI couvrant BE | 1 | 2 ou plus |
| affirmation ROI belge satisfiable | non | **possible** |
| affirmations ROI étayées | 0 sur 17 | à mesurer |

« Possible » et non « satisfaite » : lever l'impossibilité arithmétique est une
condition nécessaire. Il faudra encore que les pages retournées portent une date
— et à l'exécution du 2026-08-30, **aucune des 28 sources éligibles n'en portait
une**. C'est le chantier suivant, et la même sonde le mesure.

---

# Addendum du 2026-08-30 — résultat des sondes

**Verdict : ne ratifier aucune des quatre propositions.** Les sondes ont
contredit la proposition qui les avait motivées, ce qui est exactement leur
raison d'être.

## Sonde 1 — candidats ROI

```
domaines interrogés : energie.wallonie.be, energiesparen.be, plan.be, apere.org
by_domain           : { energie.wallonie.be: 10 }
```

Dix résultats sur dix viennent d'un seul domaine. **`plan.be` : rien.
`apere.org` : rien. `energiesparen.be` : rien.**

- **`plan.be` — ne pas inscrire.** Il ne ramène rien à la question ROI.
  L'inscrire ajouterait un domaine qui ne contribue jamais.
- **`apere.org`** — déjà inscrit, et il ne remonte pas davantage. Régler
  l'arithmétique n'aurait donc rien réglé : la seconde source aurait été un
  domaine qui ne fait jamais surface.

## Sonde 2 — élargir creg.be et economie.fgov.be à ROI

Les deux répondent, cinq documents chacun. Mais ce sont des documents de
sécurité d'approvisionnement, de capacité et de régulation nationale, dont
plusieurs très anciens :

| document | ancienneté visible |
|---|---|
| « Programme indicatif » (CREG) | cite 2001, 2002, 2004, 2005 |
| « Plan d'action national énergies renouvelables » | 7/10/2008 |
| « Étude prospective électricité » | décembre 2019 |
| « Note de la DG Énergie » | 21 juillet 2016 |

**Aucun ne porte sur la rentabilité d'une installation résidentielle.**

- **`creg.be` — ne pas élargir à ROI.** Un « Programme indicatif » de 2005
  pourrait venir corroborer une affirmation d'amortissement. C'est le pire des
  résultats : une affirmation *apparemment* corroborée.
- **`economie.fgov.be` — ne pas élargir à ROI** non plus, pour la même raison.
  `statbel.fgov.be` reste sans objet tant que ROI n'est pas le sujet.

## Réserve méthodologique

La sonde mesure ce que la **recherche retourne**, pas ce que le domaine
**contient**. `energie.wallonie.be` est massivement indexé et a occupé les dix
places. Une sonde sans concurrence (`--domain apere.org --domain plan.be`) est
la vérification qui rend le verdict ferme.

## Ce que cela établit

Vingt sources officielles interrogées avec la vraie question ROI, et **pas une
seule ne porte sur le temps de retour d'une installation résidentielle**. La
conclusion du § 5 devient l'hypothèse principale :

> La rentabilité solaire belge n'est pas une grandeur nationale. Ce sont les
> régions qui publient des chiffres de rentabilité, parce que ce sont elles qui
> en fixent les termes — tarif prosumer, certificats verts, primes,
> compensation.

Ajouter des domaines fédéraux ne réglera donc pas les 17 affirmations ROI. La
question qui reste est celle du § 5, et elle appartient au propriétaire :
**deux sources régionales concordantes, de régions différentes, peuvent-elles
établir une affirmation de rentabilité de portée belge ?**

## Ce que les sondes ont établi sur les dates

| mesure | résultat |
|---|---|
| `with_provider_date` | **0 sur 20** |
| `with_date_in_text` | 12 sur 20 |
| forme dominante | **année nue — 12 occurrences** |
| `fr_long` | 3 · `numeric` 1 · `iso` 0 · `nl_long` 0 |
| `UNDATED_CURRENT` | 2 sur 20, **correct les deux fois** |

Le champ du fournisseur est mort. Et l'année nue du corps **n'est pas une date
de publication** :

- page « investissement rentable » → `2008` (comparaison de prix), `2030` (fin
  de régime)
- page formulaires → `2022, 2024, 2021, 2013` (versions de formulaires)
- « Programme indicatif » → `2001…2005` (actes juridiques cités)

Dater sur elle daterait la page rentabilité de 2008 et pourrait dater une page
courante de 2030.

Le signal que rien ne lit aujourd'hui est ailleurs — **l'année en segment de
chemin d'URL** : 6 URL sur 9 de la passe officielle en portent une
(`/news/2025/`, `/decisions/2023/`, `/notype/2020/`), et **0 sur 10** chez
`energie.wallonie.be`. La position compte :
`/decisions/2023/fr/DECISION-252-Methodologie-tarifaire-2025-2029.pdf` — le
segment `/2023/` est la date de décision, `2025-2029` dans le nom est la période
couverte, et `…-territoire-belge-2030.pdf` est un horizon d'analyse.

Mécanisme proposé, non écrit : lire l'année **en segment de chemin**, continuer
d'ignorer les années nues du corps, garder l'extraction de validité existante.
Il ne peut que **durcir** la fraîcheur : ces pages sont aujourd'hui `UNDATED`,
donc déjà incapables d'étayer une affirmation courante. Les dater rend une page
2025 utilisable et une page 2019 explicitement périmée, au lieu d'également
inconnues.
