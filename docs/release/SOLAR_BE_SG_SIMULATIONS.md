# SOLAR_BE — Simulations de publication SG (2026-08-31)

Deux passes sur la pile locale (build de production Next + API SQLite),
produites par `tools/seo_precrawl.py`. La simulation B utilise une COPIE
de configuration (`SEOLEAD_SITE_CONFIG_DIR`) où toutes les portes sont
simulées ouvertes — la vraie configuration du dépôt n'a pas bougé :
`staging: true`, `allow_indexing: false`, offre draft, revue juridique
pendante.

### Crawl — SG — simulation A (config réelle : staging=true, allow_indexing=false, offre draft)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, LocalBusiness, PostalAddress, Question, WebSite | ✓ | 6 | 6462 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 745 c |
| `/confidentialite` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 5 | 5406 c |
| `/demande-etude` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 1594 c |
| `/llms.txt` | 404 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 9 o |
| `/outils/estimation-solaire` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1594 c |
| `/panneaux-solaires-sans-apport` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/panneaux-solaires-sans-apport | Installer des panneaux solaires sans apport en Bel | ✓ | 1 | Answer, Country, FAQPage, Question, Service, WebPage, WebSite | ✓ | 6 | 6868 c |
| `/prix-panneaux-solaires-belgique` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 27 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 110 o |

**Constats (0)**

- aucun

### Crawl — SG — simulation B (jour J : portes ouvertes dans une COPIE de test, offre validée simulée)

| Route | Statut | Robots | Canonical | Titre | Meta descr. | H1 | JSON-LD | OG | Liens int. | Texte no-JS |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 200 | index, follow | https://monprojetsolaire.be | Mon Projet Solaire | ✓ | 1 | Answer, FAQPage, LocalBusiness, PostalAddress, Question, WebSite | ✓ | 6 | 6353 c |
| `/conditions` | 200 | noindex, nofollow, nocache | https://monprojetsolaire.be/conditions | Conditions — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 636 c |
| `/confidentialite` | 200 | index, follow | https://monprojetsolaire.be/confidentialite | Protection de vos données personnelles – Solar Bel | ✓ | 1 | — | ✓ | 5 | 5297 c |
| `/demande-etude` | 200 | index, follow | https://monprojetsolaire.be/demande-etude | Demander une estimation — Mon Projet Solaire | ✓ | 1 | — | ✓ | 5 | 1485 c |
| `/llms.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 1418 o |
| `/outils/estimation-solaire` | 200 | index, follow | https://monprojetsolaire.be/outils/estimation-solaire | Cadrer votre projet solaire — Mon Projet Solaire | ✓ | 1 | — | ✓ | 6 | 1485 c |
| `/panneaux-solaires-sans-apport` | 200 | index, follow | https://monprojetsolaire.be/panneaux-solaires-sans-apport | Installer des panneaux solaires sans apport en Bel | ✓ | 1 | Answer, Country, FAQPage, Question, Service, WebPage, WebSite | ✓ | 6 | 6886 c |
| `/prix-panneaux-solaires-belgique` | 404 | noindex | — | Mon Projet Solaire | ✓ | 0 | — | — | 0 | 18 c |
| `/robots.txt` | 200 | noindex, nofollow, noarchive, nosnippet | | (text/plain) | | | | | | 109 o |
| `/sitemap.xml` | 200 | noindex, nofollow, noarchive, nosnippet | | (application/xml) | | | | | | 866 o |

**Constats (0)**

- aucun

## Ce que la simulation B a prouvé (et trouvé)

**Prouvé** : le jour J n'exige aucun développement structurel. Portes ouvertes
dans la copie de test, le site bascule d'un seul mouvement : robots
`index, follow`, bandeau de préproduction retiré, sitemap peuplé (landing
financement incluse), `/llms.txt` 200, JSON-LD Organization/LocalBusiness
avec l'identité réelle de l'opérateur, et les neuf faits SG rendus sur la
landing (25 ans, 0,27 €/kWh, 150 €, 4 %, propriété au terme) avec le bloc
de mentions obligatoires rendu verbatim (mention de simulation dans la
copie ; les mentions réelles viendront de la matrice juridique).

**Trouvé et corrigé** : la table de routes listait
`/prix-panneaux-solaires-belgique` dans le sitemap dès l'indexabilité, alors
que l'article attend toujours l'approbation propriétaire — un 404 dans le
sitemap du jour J. Les routes LANDING_PAGE adossées à du contenu ne sont
désormais listées que publiées (même règle que le footer) ; la landing
financement garde sa propre porte registre.

## Flux de leads — preuve de bout en bout (simulation A)

Soumission réelle par le proxy web (`POST /api/leads`) sur la pile locale :

- **201** — lead `7f4d97d1-…` en état `PENDING_EXPORT` ;
- qualification stockée en chaînes strictes : `known_asbestos='NO'`,
  `social_energy_tariff='NO'`, `electrical_installation_compliance='UNKNOWN'`,
  `appointment_interest='YES'`, `financing_interest='YES'` ;
- **5 cas de consentement versionnés** : processing accordé,
  followup PHONE+WHATSAPP accordés, marketing REFUSÉ (enregistré comme tel),
  partner_transfer (transmission SG) accordé ;
- attribution : canal `SEO`, landing d'origine `/panneaux-solaires-sans-apport` ;
- notification : WARNING « NOT delivered — SMTP transport not configured »
  avec la destination CONFIGURÉE — le repli honnête, bruyant, en place tant
  que les identifiants SMTP (`SEOLEAD_SMTP_*`) ne sont pas fournis sur l'hôte.
