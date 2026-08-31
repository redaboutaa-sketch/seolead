# SOLAR_BE — RC1 : réponses canoniques (GEO), maillage interne, opportunités

Trois inventaires de pré-publication. État du site au marqueur SOLAR_BE_RC1.

## 1. Réponses canoniques — une question, UNE source de réponse

Règle : chaque question clé a une page canonique qui porte la réponse
complète ; toute autre occurrence est une réponse courte qui LIE la
canonique, jamais une réponse concurrente. Vérifié sur l'état RC1 :

| Question | Source canonique | Occurrences secondaires | Conflit ? |
|---|---|---|---|
| Faut-il un apport pour installer des panneaux solaires ? | Landing `/panneaux-solaires-sans-apport` (réponse directe + FAQ) | FAQ accueil (courte, lie la landing) ; hero accueil (une phrase, lie la landing) | Non — même fond, forme courte + lien |
| Une installation peut-elle s'autofinancer ? | Landing §6 + FAQ | FAQ accueil (courte, lie la landing depuis RC1) | Non |
| Quels frais au départ ? | Landing §4 + FAQ (état sans/avec fait validé) | — | Non |
| Suis-je éligible ? | Landing §8 (critères) | Outil d'estimation (formulaire = collecte, pas réponse) | Non |
| Combien coûte une installation en Belgique ? | Article `/prix-panneaux-solaires-belgique` (EN ATTENTE d'approbation propriétaire — brouillon 8a1f6e46) | — | Non ; la landing financement renvoie le chiffrage à l'étude, elle ne donne pas de prix |
| Pourquoi pas de chiffre d'économies immédiat ? | FAQ accueil + encart de l'outil d'estimation (même texte assumé aux deux endroits) | Landing §5 (formulation propre à la formule) | Non — même position, pas de valeurs divergentes |
| Que deviennent mes données ? | `/confidentialite` (politique v1.1) | FAQ accueil (courte, lie la politique) | Non |
| Puis-je revenir sur mon consentement ? | FAQ accueil (réponse complète, sujet court) | Formulaire (cases + textes de consentement) | Non |

**Ajouts SG Solution (2026-08-31)** — les questions d'entités, chacune avec
UNE source canonique :

| Question | Source canonique | Occurrences secondaires | Conflit ? |
|---|---|---|---|
| Qui exploite Mon Projet Solaire ? | Footer (toutes pages) : « service exploité par Beaver Data Group (n° 935097675) » | Landing « Qui fait quoi » ; JSON-LD Organization (legalName) | Non — même identité partout |
| Quel est le rôle de Beaver Data Group ? | Landing « Qui fait quoi » : acquisition, qualification, consentements, rendez-vous, transmission — ni installateur, ni fournisseur, ni décisionnaire | `organization.activities` en config | Non |
| Qui propose la solution énergétique ? | Landing « Qui fait quoi » : SG Solution | Étapes du parcours (landing) | Non |
| Qui décide de l'éligibilité finale ? | Landing §4 (« La décision finale appartient à SG Solution ») + FAQ « Suis-je certain d'être accepté ? » | Aide du formulaire (préqualification) | Non — partout : SG Solution, après analyse |
| Qui vérifie la faisabilité technique ? | Landing, étapes 5 (« SG Solution analyse le dossier et vérifie la faisabilité technique ») | — | Non |
| Qui installe ? | **PERSONNE n'est nommé** — l'identité de l'installateur n'est pas fournie, donc aucune page ne la donne | — | Non (absence volontaire, blocker Owner Pack §2.6) |

Discipline pour la suite : tout nouvel article qui toucherait une de ces
questions répond en une phrase et lie la canonique — la QA `--explain` et la
table ci-dessus servent de référence de duplication.

## 2. Maillage interne — source → ancre → destination → intention

État RC1, liens en dur (le contenu publié ajoutera les siens) :

| Source | Ancre | Destination | Intention |
|---|---|---|---|
| Accueil hero | « Découvrir les solutions sans apport » | Landing financement | Requête commerciale → page dédiée |
| Accueil hero (CTA) | « Obtenir mon estimation personnalisée » | `/demande-etude` | Conversion |
| Accueil FAQ apport | « Ce que “sans apport” veut vraiment dire » | Landing financement | Approfondissement |
| Accueil FAQ autofinancement | « Les conditions d'un autofinancement approché » (RC1) | Landing financement | Approfondissement |
| Accueil FAQ données | « Politique de confidentialité » | `/confidentialite` | Confiance/RGPD |
| Accueil sections | CTA secondaires | `/outils/estimation-solaire`, `/demande-etude` | Conversion |
| Outil d'estimation (aparté) | « Ce que “sans apport” veut vraiment dire » (RC1) | Landing financement | Le visiteur qui cadre son projet découvre le financement |
| Landing hero + CTA final | « Vérifier mon projet » | `/demande-etude` | Conversion |
| Footer (toutes pages) | liens légaux | `/confidentialite`, `/conditions` | Conformité |

Tous les liens vers la landing passent par `financingLandingVisible()` : tant
qu'elle répond 404 (offre non publiable, hors staging), aucun lien ne la
désigne. Réciproque vérifiée par le crawl (0 lien cassé, 0 orphelin).

Manques assumés, à combler par le contenu : aucun lien latéral entre
articles (il n'existe qu'un article, non publié) ; le fil d'Ariane n'existe
pas (profondeur de site = 1, non bloquant).

## 3. Opportunités de contenu — 5 sujets prioritaires, briefs SEULEMENT

Aucun article n'est rédigé ici : chaque sujet exige des sources versées au
grand livre de preuves AVANT rédaction, et tout chiffre non sourcé est
bloqué par la QA. Priorité = volume estimé de la question × proximité de
l'intention commerciale × capacité à sourcer.

| # | Sujet / requête | Question posée | Intention | Page cible | Pourquoi prioritaire | Sources à verser d'abord | Liens internes prévus | CTA |
|---|---|---|---|---|---|---|---|---|
| 1 | Prime et aides photovoltaïque Wallonie 2026 | « Quelles aides pour des panneaux en Wallonie ? » | Info→commerciale | Article daté `/2026/...` | Question n°1 des PAA ; périmée chaque année — notre fraîcheur datée est l'avantage | Pages officielles Région wallonne / CWaPE (versées + arbitrées) | Landing financement (« sans apport »), demande d'étude | Étude personnalisée |
| 2 | Tarif prosumer 2026 | « Combien coûte le tarif prosumer ? » | Info | Article daté | Corpus de preuves prosumer déjà partiellement arbitré en production | CWaPE (déjà au grand livre pour partie) | Article prix, landing | Étude |
| 3 | Compteur qui tourne à l'envers / compensation | « Ai-je encore la compensation en 2026 ? » | Info | Article daté | Confusion massive, réponse régionale datée — cadre parfait pour la politique de fraîcheur | Régulateurs régionaux | Prime Wallonie (1), prix | Étude |
| 4 | Prix d'une batterie domestique Belgique | « Une batterie vaut-elle le coût ? » | Info→commerciale | Article | Le formulaire collecte déjà `battery_interest` — la demande existe dans nos propres leads | Études de prix sourçables | Prix, outil d'estimation | Étude |
| 5 | Location vs achat vs tiers-investisseur | « Faut-il acheter ou louer ses panneaux ? » | Commerciale | Article comparatif NON chiffré côté offre | Complète la landing sans-apport ; différenciation éditoriale | Sources marché + AUCUN fait d'offre hors registre | Landing financement (canonique « sans apport ») | Étude |

Garde-fous valables pour les cinq : la landing financement reste la réponse
canonique « sans apport » (les articles lient, ne répondent pas) ; tout
chiffre passe par le pipeline de preuves ; les sujets 1–3 sont datés par
segment d'URL et soumis à la politique de fraîcheur (DATED_FUTURE incluse).
