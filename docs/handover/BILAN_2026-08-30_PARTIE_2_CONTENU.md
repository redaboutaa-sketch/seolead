# Bilan seolead du 2026-08-30, partie 2 — la chaîne de contenu

Suite de `BILAN_2026-08-30_POUR_TECHFORMANORD.md`, écrit pour la même
destination. La partie 1 décrivait le consentement, la politique de
confidentialité et le contrat v2. Celle-ci couvre le seul chantier qui
conditionne l'arrivée des premiers leads : **produire un article publiable.**

Il n'y en a toujours aucun. Ce document dit où en est la chaîne, ce qui a été
réparé, ce qui reste, et ce que techformanord peut préparer en attendant.

**Aucune écriture vers techformanord n'a été faite.** Les deux variables
d'export restent absentes.

---

## 1. Le résultat en une ligne

Sept défauts corrigés et mesurés. Le pipeline produit maintenant des paquets de
recherche exploitables — 0 affirmation à risque HIGH étayée sur 57 au départ,
7 sur 83 aujourd'hui — mais **aucune exécution n'a encore passé les deux portes
de qualité simultanément.**

| exécution | brouillon | QA factuelle | QA SEO |
|---|---|---|---|
| 1 | `0916252f` | ÉCHEC — un menu de navigation affirmé | PASSÉE 90 |
| 2 | `5b33e73a` | **PASSÉE 100** | ÉCHEC — collision de titre |
| 3 | `0372ddb2` | **PASSÉE 100** | ÉCHEC — collision de titre |
| 4 | `12f12005` | ÉCHEC 67 | **PASSÉE 85** |

Chaque échec avait une cause différente, chacune a été corrigée, et aucune n'est
réapparue. Le blocage résiduel est d'une autre nature, décrit au § 4.

---

## 2. Ce qui a été réparé

### 2.1 La porte de pertinence posait une question et notait la réponse à une autre

La passe ciblée interroge un domaine officiel avec **sa propre** requête
(« premie zonnepanelen Vlaanderen voorwaarden officieel ») parce que la requête
de l'article ne ferait jamais remonter cette page. Le repliement perdait cette
requête, et la porte notait la réponse contre la requête de l'article.
Résultat : **31 sources officielles sur 40 écartées**, dont la totalité de
vlaanderen.be et de creg.be.

Chaque source porte désormais la requête qui l'a produite. Seuils inchangés,
règle dure inchangée — un résultat réellement hors sujet reste écarté.

Mesuré : rejets 31 → 22, sources éligibles 19 → 28.

### 2.2 Trois étiquetages faux réclamaient des preuves impossibles

- **`eur` cherché en sous-chaîne.** Il figure dans *chaleur*, *onduleur*,
  *meilleur*, *heures*, *capteur*, *valeur*. « Les panneaux n'aiment pas les
  fortes chaleurs » devenait une affirmation de prix de marché exigeant trois
  sources concordantes.
- **`kwh` traité comme un indice de prix.** Toute quantité d'énergie devenait
  une affirmation tarifaire à risque HIGH exigeant une source institutionnelle
  datée.
- **La détection de région retenait la première sous-région de l'énumération**,
  donc toujours la wallonne. Une page couvrant les trois régions belges — donc
  précisément une source nationale — était étiquetée wallonne puis rejetée pour
  « portée régionale incompatible ».

Mesuré sur le paquet réel : 23 affirmations sur 139 étaient tenues à une barre
qu'elles n'avaient aucune raison d'atteindre. Risque HIGH 57 → 49, MEDIUM 32 →
17.

### 2.3 Un menu de navigation était affirmé comme un fait

Un extracteur markdown rend une barre de navigation sur une seule ligne. Le
texte porte le vocabulaire d'une page de primes : il a été classé SUBSIDY à
risque HIGH, est resté non étayé, et la QA a conclu que le brouillon
l'affirmait. C'était l'unique point bloquant de l'exécution 1.

### 2.4 Trois défauts de mesure et d'ergonomie

- Le rapport d'exécution annonçait « 10 sources évaluées, 0 écartée » alors que
  50 étaient récupérées et 22 écartées : le résumé était pris avant la passe
  officielle et jamais repris.
- La commande de relecture de paquet comparait la région à une valeur calculée
  autrement, et signalait 114 changements dont presque aucun n'était réel.
- Le garde anti-doublon de titre comparait à **tous** les brouillons jamais
  écrits, tous mots-clés confondus. Le rédacteur étant amorcé par le titre du
  brief, toute relance se heurtait à son propre prédécesseur : trois brouillons
  du même mot-clé se bloquaient mutuellement. Deux exécutions payantes ont servi
  à le découvrir. La cannibalisation exige deux URL ; tous les brouillons d'un
  mot-clé partagent un slug. La collision ne vaut plus qu'entre mots-clés
  différents.

---

## 3. Effet net, mesuré

| indicateur | avant | après |
|---|---|---|
| sources récupérées | 50 | 50 |
| sources éligibles | 19 | **28** |
| affirmations HIGH étayées | **0** / 57 | **7** / 83 |
| affirmations totales | 139 | 212 |
| affirmations étayées | — | 109 |

Suite de tests : 815 passés, 7 ignorés. Chaque correctif est tenu par une
mutation qui le fait tomber s'il est défait.

---

## 4. Ce qui bloque encore, et ce n'est plus un défaut

Trois obstacles subsistent. Aucun n'est un bug : ce sont des limites de la
matière disponible et une propriété du rédacteur.

### 4.1 Aucune source datée, sur 28

Chaque page officielle ressort avec `published_at: null`. Or les catégories
SUBSIDY et GRID_RULE exigent la fraîcheur. Sept pages s'en sortent par un
marqueur textuel (« en vigueur », « actuellement ») ; quatre sont franchement
périmées — des primes flamandes closes en 2021, 2022, 2025 — et leur rejet est
**juste** : un article qui les présenterait comme actuelles serait faux.

C'est la contrainte dominante sur les 76 affirmations HIGH encore bloquées.

### 4.2 Aucune autorité belge du retour sur investissement

La requête ROI n'interroge que trois domaines et ne ramène que du wallon. Les
affirmations de ROI portent la Belgique par défaut du marché, et la règle de
portée régionale — correcte — refuse qu'une source wallonne établisse une
affirmation belge. Dix-sept affirmations à risque HIGH sont dans ce cas, sur un
article dont le sujet *est* la rentabilité.

C'est un trou dans le registre d'autorités, pas une erreur de code.

### 4.3 Le rédacteur est stochastique

Les couches déterministes — recherche, pertinence, extraction, étiquetage,
preuve — donnent maintenant le même résultat d'une exécution à l'autre. Le
rédacteur, non. Sur quatre exécutions, il a échoué quatre fois pour trois
raisons différentes, et n'a jamais franchi les deux portes le même jour.

**Conséquence opérationnelle : la production d'articles n'est pas encore
fiable.** Elle produit des paquets de recherche solides, et un texte dont la
conformité est tirée au sort. C'est le prochain sujet.

### 4.4 Ce que « QA verte » ne garantit pas

Un brouillon a obtenu 100/100 en QA factuelle. Lu, il ne dit presque rien : un
seul chiffre dans tout l'article, et une FAQ qui répond « cela varie selon
plusieurs facteurs » à « quelle est la rentabilité moyenne ? ». Le paquet
*contient* la réponse — « 6 à 9 ans », « 7,3 % à 8,4 % » — mais toutes ces
affirmations sont bloquées par le § 4.2.

La QA certifie que chaque phrase trace vers une preuve. Elle ne certifie pas que
l'article soit utile. Tant que les § 4.1 et 4.2 tiennent, les articles produits
seront conformes et creux.

---

## 5. Pour techformanord : ce que cela change, et ce qui ne change pas

### Ce qui ne change pas

- **Le contrat v1 n'a pas bougé.** Empreinte armée au `2026-08-16T17:34:58Z`,
  intacte. Aucun DTO modifié.
- **Les quatre arbitrages v2 sont consignés** dans
  `docs/integrations/PROSPECT360_INGEST_CONTRACT_V2_PROPOSAL.md`, addendum du
  2026-08-30 : `consents[]` avec unicité `(purpose, channel)` et clé de tri
  explicite, `PARTNER_TRANSFER` refusé ⇒ lead accepté et marqué non
  transmissible, route `/api/v2/lead-ingest` sans champ de version dans le
  corps, refus transmis avec un statut `refused` distinct de `revoked`.
- **Rien n'est implémenté côté v2** et rien ne le sera avant que le digest
  golden v2 existe.

### Ce qui change

Le calendrier. La partie 1 disait « contenu → passage en public → variables
d'export ». La première étape n'est pas franchie, et le § 4.3 dit qu'elle ne le
sera pas de façon fiable sans un travail supplémentaire sur le rédacteur.

**Aucun lead n'arrivera tant qu'un article n'est pas en ligne.** Ce n'est pas
une question de jours mais d'un verrou qui reste à lever.

### Ce que techformanord peut préparer sans dépendre de nous

1. **Figer le digest golden v2** et son arming record. Rien ne l'empêche : les
   quatre décisions de structure sont prises, et le producteur n'a pas besoin
   d'exister pour que la charge canonique soit spécifiée et gelée côté
   plateforme.
2. **Trancher les deux points restés ouverts** au § « Ce qui reste ouvert » de
   l'addendum : le registre des identifiants de campagne, et la sémantique de
   version d'un texte traduit. Le second doit être réglé **avant** la première
   charge portant une locale `nl`.
3. **Étendre le statut de consentement avec `refused`**, distinct de `revoked`.
   La distinction existe déjà côté seolead (`lead_consent.granted = false` au
   moment de la collecte, par opposition à un retrait ultérieur), et c'est celle
   qu'un régulateur interroge.
4. **Préparer la route `/api/v2/lead-ingest`** en 422 franc sur toute charge
   non conforme, `extra: "forbid"` fermé des deux côtés.

Aucun de ces quatre points n'attend seolead.

---

## 6. Suspens, par responsable

### Chez le propriétaire / le juridique

- Traduction NL des quatre textes de consentement par un locuteur natif, puis
  validation. Une version par locale. Bloque la route `/nl/demande-etude` et,
  par la garde de configuration, le passage du site en public.
- Libellés NL non juridiques du formulaire.

### Chez techformanord

- Les quatre points du § 5 ci-dessus.

### Chez seolead

- Fiabiliser le rédacteur (§ 4.3) — le prochain sujet de fond.
- Extraction de date des pages officielles (§ 4.1).
- Autorité belge du ROI dans le registre (§ 4.2).
- Publier un premier article.
- Passage en public : `staging: false`, `allow_indexing: true`, variables web,
  en-tête Traefik, retrait du bandeau.
- Définir `PROSPECT360_INGEST_URL` et `PROSPECT360_CREDENTIAL` — en dernier.
- Jamais fait : une soumission de formulaire de bout en bout depuis un
  navigateur. `lead_consent` doit alors compter **5 lignes** pour un lead
  complet.

---

## 7. Références

| sujet | fichier ou identifiant |
|---|---|
| Bilan partie 1 | `docs/handover/BILAN_2026-08-30_POUR_TECHFORMANORD.md` |
| Contrat v1, empreinte armée | `docs/integrations/PROSPECT360_INGEST_CONTRACT.md` |
| Contrat v2 + arbitrages | `docs/integrations/PROSPECT360_INGEST_CONTRACT_V2_PROPOSAL.md` |
| Appariement requête ↔ source | `app/services/relevance.py`, `authoritative_research.py` |
| Étiquetage des affirmations | `app/services/claim_policy.py`, `region.py` |
| Extraction d'affirmations | `app/services/claim_extraction.py` |
| Collision de titre | `app/services/title_registry.py` |
| Relecture d'un paquet scellé | `seolead package replay <id>` |

Aucun secret ne figure dans ce document : seuls des **noms** de variables
d'environnement sont cités, jamais leurs valeurs.

---

# Addendum du 2026-08-31 — campagne FR uniquement

**Décision du propriétaire.** Cette campagne est francophone. Le néerlandais
servira une future campagne énergie aux Pays-Bas, pas celle-ci.

## Ce qui change

`config/sites/solar_be.yaml` ne déclare plus que `supported_languages: [fr]`.
Les routes `/` et `/demande-etude` ne déclarent plus que la locale française, et
`/nl/demande-etude` cesse d'être servie — elle répond 404.

## Conséquence assumée, écrite pour ne pas être oubliée

**Le marché flamand n'est pas adressé par cette campagne.** Un visiteur
néerlandophone en Belgique voit le site en français ; aucune page ne lui est
servie dans sa langue, et aucun lead flamand n'est capté par ce site. Un
formulaire soumis avec `language: nl` — page en cache, signet, robot — est
étiqueté `fr` plutôt que transmis tel quel : la charge ne prétend pas adresser
un marché qu'elle n'adresse pas.

C'est un choix commercial, et le genre de choix qu'on oublie et qu'on prend six
mois plus tard pour un oubli technique.

## Rien de la mécanique néerlandaise n'est supprimé

Routes, chaîne i18n, libellés placeholders « À TRADUIRE PAR UN NATIF » : tout
reste. Le fichier de route existe encore et refuse simplement de servir une
locale que le site ne déclare pas — le supprimer jetterait une plomberie qui
fonctionne et qu'une campagne néerlandaise redemandera.

Remettre `nl` dans `supported_languages` rallume l'ensemble. Et la garde
`pending_legal_review` se remet aussitôt à bloquer la sortie de staging, parce
que les textes NL sont toujours des placeholders. C'est le comportement voulu,
pas un reliquat — un test l'épingle.

## Le verdict qui compte

```
locales supportées : ['fr']
staging            : True
allow_indexing     : False

La configuration accepte-t-elle staging: false ?
  ACCEPTÉE — la garde pending_legal_review ne bloque plus.
    is_publishable = True
    is_indexable   = False   (allow_indexing encore false)

Et si on remettait nl sans textes validés ?
  REFUSÉE, comme voulu.
```

**La garde de sortie de staging est verte.** Ce n'est pas un affaiblissement :
la règle interdit qu'une locale SERVIE collecte un consentement sur un texte non
validé, et la locale qu'elle protégeait n'est plus servie.

Deux décisions restent distinctes, et la seconde n'est pas prise :
`staging: false` rend le site public ; `allow_indexing: true` le rend
indexable. Le bandeau de préproduction et `noindex,nofollow` sont toujours en
place.

## Ce qui reste suspendu au juridique

La traduction NL des quatre textes de consentement **n'est plus bloquante pour
cette campagne**. Elle redevient un prérequis le jour où une campagne
néerlandophone démarre, et la garde l'imposera d'elle-même.
