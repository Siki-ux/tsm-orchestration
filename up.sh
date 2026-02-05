#!/usr/bin/env bash
# Start all TSM services
# Usage:
#   ./up.sh           - Start base TSM services only
#   ./up.sh --all     - Start TSM + water_dp-api services
#   ./up.sh --water   - Start TSM + water_dp-api services

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" == "--all" ]] || [[ "$1" == "--water" ]]; then
    echo "Starting TSM + water_dp-api services..."
    docker compose -f "${DIR_SCRIPT}/docker-compose.yml" -f "${DIR_SCRIPT}/docker-compose-water-dp.yml" up -d
else
    echo "Starting base TSM services..."
    docker compose -f "${DIR_SCRIPT}/docker-compose.yml" up -d
fi