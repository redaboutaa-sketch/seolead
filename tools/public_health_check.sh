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

echo "-- sitemap (aucun draft/pending, jamais la landing financement) --"
curl -s "$BASE/sitemap.xml" | grep -o '<loc>[^<]*</loc>'
if curl -s "$BASE/sitemap.xml" | grep -q "panneaux-solaires-sans-apport"; then
  echo "FAIL: la landing financement est au sitemap alors que l'offre n'est pas publiable"; FAIL=1
fi

[ "$FAIL" = 0 ] && echo "== VERDICT: OK ==" || echo "== VERDICT: FAIL — voir lignes FAIL ci-dessus =="
exit $FAIL
