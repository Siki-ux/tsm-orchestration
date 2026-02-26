#!/usr/bin/env bash
# Start all TSM services (stripped for water_dp)
# Usage:
#   ./up.sh           - Start TSM + water_dp services (default)
#   ./up.sh --base    - Start base TSM services only (no water_dp)
#   ./up.sh --full    - Start ALL TSM services (no strip, no water_dp)

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

COMPOSE_BASE="-f ${DIR_SCRIPT}/docker-compose.yml"
COMPOSE_STRIP="-f ${DIR_SCRIPT}/docker-compose.override.strip.yml"
COMPOSE_WATER="-f ${DIR_SCRIPT}/docker-compose-water-dp.yml"

if [[ "$1" == "--full" ]]; then
    echo "Starting ALL TSM services (unstripped, no water_dp)..."
    docker compose ${COMPOSE_BASE} up -d
elif [[ "$1" == "--base" ]]; then
    echo "Starting stripped TSM services only (no water_dp)..."
    docker compose ${COMPOSE_BASE} ${COMPOSE_STRIP} up -d
else
    echo "Starting TSM + water_dp services..."
    docker compose ${COMPOSE_BASE} ${COMPOSE_STRIP} ${COMPOSE_WATER} up -d
fi