# Runbook — Google Search Console + Bing Webmaster Tools

Prérequis (acquis le 2026-08-31) : site LIVE et indexable, sitemap publié,
mécanisme de vérification en place — `seo.verification.google` émet
`<meta name="google-site-verification">`, `seo.verification.bing` émet
`<meta name="msvalidate.01">`, null n'émet rien. Les jetons ne sont PAS des
secrets : ils sont publiés dans le HTML de chaque page par construction —
ils peuvent vivre dans le dépôt.

## 1. Google Search Console — créer la propriété

1. https://search.google.com/search-console → « Ajouter une propriété ».
2. Choisir **« Préfixe d'URL »** avec `https://monprojetsolaire.be`
   — PAS « Domaine » : la propriété Domaine n'accepte que la vérification
   DNS (TXT), alors que notre mécanisme est la balise HTML. (La vérification
   DNS reste possible si vous préférez : un TXT chez votre registrar, et
   aucun jeton dans la config — mais le chemin outillé est la balise.)
3. Méthode de vérification : **« Balise HTML »**. Google affiche
   `<meta name="google-site-verification" content="XXXXXXXX" />`.
4. Copier UNIQUEMENT la valeur de `content` (le XXXXXXXX, sans la balise).
5. **Ne pas cliquer « Vérifier » tout de suite** — la balise doit d'abord
   être servie (étapes 3-4).

## 2. Bing Webmaster Tools — créer le site

Option A (la plus simple, aucun jeton) : https://www.bing.com/webmasters →
« Importer vos sites depuis Google Search Console » — Bing reprend la
propriété vérifiée et le sitemap. Dans ce cas `seo.verification.bing`
reste null, et c'est correct.

Option B (manuelle) : « Ajouter votre site manuellement » →
`https://monprojetsolaire.be` → méthode **« Balise Meta »** →
copier la valeur `content` de `<meta name="msvalidate.01" content="YYYY" />`.

## 3. Poser les jetons dans la configuration

`config/sites/solar_be.yaml` :

```yaml
seo:
  verification:
    google: "XXXXXXXX"     # la valeur content, entre guillemets
    bing: null             # ou "YYYY" si option B
```

Par le dépôt, jamais par une édition locale qui divergerait de git :
commit + push (ou coller les jetons dans la conversation Claude Code — ils
sont publics par construction — et la PR est faite pour vous), puis `git
pull` sur l'hôte.

## 4. Déployer — c'est l'API qui porte la config

`config/` est copié dans l'image `seolead_api` (le web lit la config via
l'API et rafraîchit sous 60 s) :

```bash
cd /opt/seolead && git pull origin main
docker compose -f docker-compose.yml -f infra/traefik/docker-compose.public.yml build seolead_api
docker compose -f docker-compose.yml -f infra/traefik/docker-compose.public.yml up -d --force-recreate seolead_api
```

Vérifier que la balise est servie (attendre ~60 s de cache web) :

```bash
curl -s https://monprojetsolaire.be/ | grep -o 'name="google-site-verification" content="[^"]*"'
curl -s https://monprojetsolaire.be/ | grep -o 'name="msvalidate.01" content="[^"]*"'   # si option B
```

## 5. Vérifier les propriétés

Retour dans chaque console → « Vérifier ». La propriété passe vérifiée et
le reste tant que la balise est servie — ne jamais retirer le jeton de la
config ensuite.

## 6. Soumettre le sitemap

- Search Console → Sitemaps → saisir `sitemap.xml` → Envoyer.
- Bing → Sitemaps → `https://monprojetsolaire.be/sitemap.xml`.

Le sitemap ne liste que le publiable (jamais une page noindex, jamais la
landing fermée) — c'est mécanique, rien à filtrer à la main.

## 7. Demander l'indexation — dans cet ordre, et rien d'autre

Search Console → « Inspection de l'URL » → coller l'URL → « Demander une
indexation » (quota ~10/jour, largement suffisant) :

1. `https://monprojetsolaire.be/`
2. `https://monprojetsolaire.be/rentabilite-panneaux-solaires-belgique`
3. `https://monprojetsolaire.be/outils/estimation-solaire`
4. `https://monprojetsolaire.be/demande-etude`

Ne JAMAIS demander : `/prix-panneaux-solaires-belgique` (noindex tant que
non rafraîchie), `/conditions` (noindex), `/panneaux-solaires-sans-apport`
(404 voulu), `/confidentialite` (dans le sitemap, elle suivra seule).

## 8. Remplir le suivi — à partir de là, jamais avant

`docs/seo/SOLAR_BE_INDEXATION_TRACKING.md` :

- « Google indexed » / « Bing indexed » : depuis Inspection de l'URL /
  rapport Couverture uniquement — crawlable n'est pas indexed.
- Table hebdomadaire : depuis Performance (impressions, clics, CTR,
  position) — les premières données apparaissent sous 2-3 jours.
- Aucune valeur estimée, aucune case remplie « en attendant ».
