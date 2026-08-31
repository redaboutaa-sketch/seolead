# SOLAR_BE — Préparation MCP : matrice de préparation, AUCUNE implémentation

Périmètre RC1 : préparation seulement. Aucun serveur MCP n'est implémenté ni
implémenté « à moitié » — ce document dit ce qui serait exposable, sur quelle
primitive existante chaque outil s'appuierait, ce qui manque, et ce qui
bloque. La règle du site vaut pour un agent comme pour un humain : rien ne se
dit qui ne soit validé, rien ne se collecte sans consentement explicite.

## Matrice

| Outil futur | Service existant (primitive) | Primitive manquante | Autorisation requise | Données personnelles ? | Consentement ? | Prêt |
|---|---|---|---|---|---|---|
| `get_site_info` (marque, périmètre, méthode) | `GET /site/v1/sites/{id}` (DTO complet) + `/llms.txt` | Version publique NON authentifiée et filtrée du DTO (l'API actuelle est interne, clé requise, et expose des champs de pilotage) | Aucune (lecture publique) | Non | Non | **NON** — primitive publique à créer |
| `get_solar_offer` / `get_financing_options` | Registre d'offre (`app/site/offer.py`, `usable_facts` fail-closed) | Idem : exposition publique en lecture ; le filtrage validé-seulement existe déjà | Aucune | Non | Non | **NON** — bloqué de toute façon tant que l'offre n'est pas publiable (portes A2+B) ; le fail-closed rend l'outil « honnêtement vide » dès la primitive créée |
| `get_published_articles` / `get_article` | `listPublished` / contenu publié (API site) | Version publique non authentifiée | Aucune | Non | Non | **NON** — même primitive publique manquante ; contenu = 0 article publié à ce jour |
| `answer_question` (réponses canoniques) | Table des réponses canoniques (`docs/seo/RC1_GEO_LIENS_CONTENUS.md` §1) + FAQ des pages | Les réponses canoniques ne sont pas servies comme DONNÉES (elles vivent dans le JSX) ; il faudrait les extraire en source structurée unique | Aucune | Non | Non | **NON** — refactoring données-d'abord requis |
| `check_eligibility` (pré-qualification) | Critères de la landing (§8) + étapes du formulaire (config `form_steps`) | Moteur de règles d'éligibilité (aucune règle mécanique n'existe : l'éligibilité est jugée par un humain à l'étude) | Aucune pour la version « voici les critères » ; interdit au-delà | Potentiellement (si l'agent transmet la situation du visiteur) | Oui si des données de situation sont traitées | **NON** — et la version « moteur de décision » est HORS périmètre tant que l'étude est humaine |
| `request_study` (soumission d'une demande par agent) | `POST` capture de lead + registre de consentement versionné (5 cases, versions) | Parcours de consentement AGENT : le consentement actuel est capturé par cases cochées par un humain sur le site ; aucun mécanisme ne prouve un consentement recueilli par un agent tiers | Clé/enregistrement de l'agent appelant + anti-abus (le pot de miel actuel présume un navigateur) | **Oui** (identité, contact, projet) | **Oui — bloquant** : la préuve de consentement par canal agent n'existe pas | **NON — le plus loin d'être prêt ; ne pas exposer en premier** |
| `get_claim_evidence` (« d'où vient ce chiffre ? ») | Grand livre de preuves (claims arbitrés, sources, dates) | Exposition publique en lecture seule d'un sous-ensemble (claims employés par du contenu publié uniquement) | Aucune | Non | Non | **NON** — mais différenciateur fort ; à cadrer après publication du premier article |

## Lecture de la matrice

- **Le goulot unique** : il n'existe AUCUNE surface publique non authentifiée
  côté API — c'est un choix de sécurité actuel (clé interne partout). La
  première brique MCP réelle est une façade publique en lecture seule,
  filtrée, sans données de pilotage. Tout le reste en découle.
- **Ce qui est déjà juste** : le registre d'offre fail-closed donne des
  réponses honnêtes par construction (« aucune offre validée » tant que les
  portes ne sont pas franchies) ; le consentement versionné est le bon socle
  pour un futur canal agent — il manque le canal, pas le registre.
- **Ordre recommandé le jour où le propriétaire ouvre ce chantier** :
  1. façade publique lecture seule (info site + offre + contenu publié) ;
  2. `answer_question` après extraction des réponses canoniques en données ;
  3. `get_claim_evidence` (différenciation) ;
  4. `request_study` en DERNIER, après cadrage juridique du consentement
     par canal agent (nouvelle entrée au registre de consentement, champ
     canal déjà versionné).
- **`/llms.txt`** reste le contrat de lecture passif pour les agents non-MCP ;
  il est déjà derrière la porte d'indexation.
