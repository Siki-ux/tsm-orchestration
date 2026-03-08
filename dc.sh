#!/usr/bin/env bash
# Pass-through wrapper for docker compose with strip override
# Usage: ./dc.sh ps, ./dc.sh logs frost, ./dc.sh down, etc.

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

docker compose \
    -f "${DIR_SCRIPT}/docker-compose.yml" \
    -f "${DIR_SCRIPT}/docker-compose-water-dp.yml" \
    "$@"