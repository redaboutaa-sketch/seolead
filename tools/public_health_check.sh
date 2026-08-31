#!/bin/sh
# Contrôle de santé public — reproductible, lecture seule, zéro secret.
#
#   sh tools/public_health_check.sh [https://monprojetsolaire.be]
#
# Chaque ligne : ROUTE  ATTENDU  CONSTATÉ  VERDICT. Le 404 de la landing
# financement est un état VOULU (offre non publiable — revue juridique
# pendante) et sort en EXPECTED_GATED_404, jamais en incident.
set -u
BASE="${1:-https://monprojetsolaire.be}"
FAIL=0

# Après un `up -d --force-recreate`, Traefik ne route pas tant que le
# conteneur web n'est pas passé `healthy` (~30 s) : tout répond 404 pendant
# cette fenêtre. Mesuré le 2026-08-31 — la santé lancée trop tôt a crié FAIL
# sur un site parfaitement sain. On attend donc le routeur avant de juger.
tries=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/robots.txt")" = "200" ]; do
  tries=$((tries + 1))
  if [ "$tries" -ge 12 ]; then
    echo "AVERTISSEMENT: $BASE/robots.txt ne répond pas 200 après 60 s — le routeur est peut-être réellement en panne; les lignes ci-dessous jugent l'état actuel."
    break
  fi
  sleep 5
done

check() { # path expected_code label
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$1")
  if [ "$code" = "$2" ]; then verdict="OK"; else verdict="FAIL"; FAIL=1; fi
  printf '%-42s attendu %-3s constaté %-3s %s %s\n' "$1" "$2" "$code" "$verdict" "${3:-}"
}

robots_meta() { # path expected_fragment
  meta=$(curl -s "$BASE$1" | grep -o 'name="robots" content="[^"]*"' | head -1)
  case "$meta" in
    *"$2"*) printf '%-42s meta robots: %s OK\n' "$1" "$meta" ;;
    *) printf '%-42s meta robots: %s FAIL (attendu: %s)\n' "$1" "${meta:-ABSENT}" "$2"; FAIL=1 ;;
  esac
}

echo "== Santé publique — $BASE — $(date -u +%Y-%m-%dT%H:%MZ) =="
check /                                   200
check /prix-panneaux-solaires-belgique    200
check /rentabilite-panneaux-solaires-belgique 200 "(après publication de la révision 2)"
check /demande-etude                      200
check /outils/estimation-solaire          200
check /confidentialite                    200
check /conditions                         200 "(noindex voulu — texte légal en attente)"
check /robots.txt                         200
check /sitemap.xml                        200
check /llms.txt                           200
check /panneaux-solaires-sans-apport      404 "EXPECTED_GATED_404 — offre non publiable, voulu"

robots_meta /                             "index, follow"
robots_meta /conditions                   "noindex"

# Les DEUX signaux, pas seulement la meta : au lancement, un en-tête
# X-Robots-Tag: noindex résiduel contredisait la meta index,follow et Google
# a suivi le plus strict — trois demandes d'indexation refusées avant que
# quiconque ne lise les en-têtes. Une page publique n'en porte AUCUN ;
# /preview le garde inconditionnellement.
hdr=$(curl -s -o /dev/null -w '%{header_json}' "$BASE/" | grep -io '"x-robots-tag"' || true)
if [ -n "$hdr" ]; then
  echo "/                                          en-tête X-Robots-Tag PRÉSENT — FAIL (il contredit la meta, Google suit le plus strict)"; FAIL=1
else
  echo "/                                          en-tête X-Robots-Tag: absent OK"
fi
# /preview a DEUX gardes légitimes selon d'où on regarde. En production,
# la basicauth Traefik répond 401 à l'edge : la requête n'atteint jamais
# l'application, rien n'est servi, rien n'est indexable — l'absence
# d'en-tête sur ce 401 est correcte (mesuré le 2026-08-31 : exiger
# l'en-tête ici a crié FAIL sur un site parfaitement fermé). En local,
# sans Traefik, c'est le middleware Next qui répond, avec l'en-tête.
# Ce qui est interdit : un préview SERVI (2xx/4xx applicatif) sans en-tête.
pcode=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/preview/fr/x")
phdr=$(curl -s -o /dev/null -w '%{header_json}' "$BASE/preview/fr/x" | grep -io '"x-robots-tag"' || true)
if [ "$pcode" = "401" ]; then
  echo "/preview/*                                 401 basicauth à l'edge OK (jamais servi, donc jamais indexable)"
elif [ -n "$phdr" ]; then
  echo "/preview/*                                 en-tête X-Robots-Tag: présent OK (jamais indexable)"
else
  echo "/preview/*                                 servi ($pcode) SANS en-tête X-Robots-Tag ni 401 — FAIL"; FAIL=1
fi

echo "-- sitemap (aucun draft/pending, jamais la landing financement) --"
curl -s "$BASE/sitemap.xml" | grep -o '<loc>[^<]*</loc>'
if curl -s "$BASE/sitemap.xml" | grep -q "panneaux-solaires-sans-apport"; then
  echo "FAIL: la landing financement est au sitemap alors que l'offre n'est pas publiable"; FAIL=1
fi

[ "$FAIL" = 0 ] && echo "== VERDICT: OK ==" || echo "== VERDICT: FAIL — voir lignes FAIL ci-dessus =="
exit $FAIL
