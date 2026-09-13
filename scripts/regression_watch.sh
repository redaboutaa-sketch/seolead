#!/usr/bin/env bash
# Veille de régression nocturne — relire les pages publiées sous les règles
# du jour. Lecture seule : rien n'est écrit, publié ni approuvé.
#
# Installé dans la crontab de root sur l'hôte :
#   17 3 * * * /opt/seolead/scripts/regression_watch.sh >> /var/log/seolead-watch.log 2>&1
#
# 3 h 17 plutôt que 3 h 00 : rien d'autre ne tourne à cette minute-là, et une
# heure ronde est la première que tout le monde choisit.
#
# Le code de sortie EST l'alerte. 0 = tout va bien et cron reste muet ;
# 1 = au moins une page a régressé, cron envoie la sortie par courriel à
# root si un MTA est configuré, et la ligne reste dans le journal sinon.
set -euo pipefail

RACINE="${SEOLEAD_ROOT:-/opt/seolead}"
COMPOSE=(docker compose -f "${RACINE}/docker-compose.yml"
         -f "${RACINE}/infra/traefik/docker-compose.public.yml")

cd "${RACINE}"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) veille de régression ==="

if ! "${COMPOSE[@]}" ps --status running --services | grep -qx seolead_api; then
    echo "seolead_api n'est pas démarré : la veille ne peut pas conclure." >&2
    exit 2   # ni sain ni régressé : indéterminé, et il faut le distinguer.
fi

"${COMPOSE[@]}" exec -T seolead_api seolead site watch --site "${1:-solar_be}"
