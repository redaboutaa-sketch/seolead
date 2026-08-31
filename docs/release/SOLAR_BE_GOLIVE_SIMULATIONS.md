# SOLAR_BE — Simulations GO-LIVE (2026-08-31)

Trois passes finales avant l'ouverture des portes. B et « état réel » ont
tourné sur une COPIE de configuration et une COPIE de base de test (ligne
d'article étiquetée [SIMULATION B] — l'article réel, révision 2, vit dans
la base de production et y est publié par le CLI).

## Simulation A — rien ne s'est ouvert pendant la PR

Config réelle du dépôt au moment du test : accueil 200 + noindex +
bandeau préproduction + llms.txt 404. PASS.

### Crawl — GO-LIVE — simulation B (jour J complet : portes ouvertes en copie de test, article publié simulé)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | index, follow | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, LocalBusiness, PostalAddress, Question, WebSite | ✓ | 7 | 6422 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 644 c |
| `/confidentialite` | 200 | index, follow | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 6 | 5305 c |
| `/demande-etude` | 200 | index, follow | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1493 c |
| `/llms.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 1565 o |
| `/outils/estimation-solaire` | 200 | index, follow | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 7 | 1493 c |
| `/panneaux-solaires-sans-apport` | 200 | index, follow | https://monprojetsolaire.be/panneaux-solaires-sans-apport | Installer des panneaux solaires sans apport en Bel | ✓ | 1 | Answer, Country, FAQPage, Question, Service, WebPage, WebSite | ✓ | 7 | 6894 c |
| `/prix-panneaux-solaires-belgique` | 200 | index, follow | https://monprojetsolaire.be/prix-panneaux-solaires-belgique | [SIMULATION B] Prix des panneaux solaires en Belgi | ✓ | 1 | Article, BreadcrumbList, ListItem, WebSite | ✓ | 6 | 1575 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 109 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 931 o |

**Constats (0)**

- aucun

### Crawl — GO-LIVE — état réel de publication (portes ouvertes, offre draft : landing fermée)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | index, follow | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, LocalBusiness, PostalAddress, Question, WebSite | ✓ | 6 | 6171 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 644 c |
| `/confidentialite` | 200 | index, follow | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 6 | 5305 c |
| `/demande-etude` | 200 | index, follow | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1493 c |
| `/llms.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 834 o |
| `/outils/estimation-solaire` | 200 | index, follow | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1343 c |
| `/panneaux-solaires-sans-apport` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/prix-panneaux-solaires-belgique` | 200 | index, follow | https://monprojetsolaire.be/prix-panneaux-solaires-belgique | [SIMULATION B] Prix des panneaux solaires en Belgi | ✓ | 1 | Article, BreadcrumbList, ListItem, WebSite | ✓ | 6 | 1575 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 109 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 791 o |

**Constats (0)**

- aucun

## L'état réel de publication (portes ouvertes, offre draft)

C'est l'état exact que la production aura au jour J tant que la revue
juridique n'a pas levé `pending_legal_review` :

- landing financement → **404**, aucun lien entrant nulle part (hero, FAQ,
  outil : tous derrière la même porte), absente du sitemap — la porte
  logicielle n'est PAS contournée ;
- article prix → 200, index/follow, canonical, JSON-LD Article+Breadcrumb,
  dans le sitemap ;
- accueil → index/follow, bandeau retiré, Organization/LocalBusiness à
  l'identité réelle de l'opérateur ;
- /conditions → servie, noindex (texte légal en attente), retirée du
  sitemap (correctif de cette passe : un sitemap ne liste pas une page qui
  se déclare noindex) ;
- llms.txt → 200 ; robots.txt ouvert ; crawl : 0 constat.
