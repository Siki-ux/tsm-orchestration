#!/usr/bin/env bash
# Start all TSM services (stripped for water_dp)
# Usage:
#   ./up.sh           - Start TSM + water_dp services (default)
#   ./up.sh --base    - Start base TSM services only (no water_dp)
#   ./up.sh --full    - Start ALL TSM services (no strip, no water_dp)

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PODMAN_MODE=false
TARGET_MODE=""

for arg in "$@"; do
    if [[ "$arg" == "--podman" ]]; then
        PODMAN_MODE=true
    elif [[ "$arg" == "--full" || "$arg" == "--base" ]]; then
        TARGET_MODE="$arg"
    fi
done

COMPOSE_CMD="docker compose"
COMPOSE_BASE="-f ${DIR_SCRIPT}/docker-compose.yml"

if [[ "$PODMAN_MODE" == "true" ]]; then
    echo "======================================================================================"
    echo " WARNING: Running in Podman mode."
    echo " If 'proxy' fails to start, ensure you have enabled unprivileged ports on your host:"
    echo "   sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80"
    echo "======================================================================================"
    COMPOSE_CMD="podman compose"
    export UID=$(id -u)
    export GID=$(id -g)
    COMPOSE_BASE="-f ${DIR_SCRIPT}/docker-compose.yml -f ${DIR_SCRIPT}/docker-compose.override.podman.yml"
fi

COMPOSE_WATER="-f ${DIR_SCRIPT}/docker-compose-water-dp.yml"

if [[ "$TARGET_MODE" == "--full" ]]; then
    echo "Starting ALL TSM services (unstripped, no water_dp)..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d
elif [[ "$TARGET_MODE" == "--base" ]]; then
    echo "Starting stripped TSM services only (no water_dp)..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d
else
    echo "Starting TSM + water_dp services..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} ${COMPOSE_WATER} up -d
fi