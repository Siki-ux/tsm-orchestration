#!/usr/bin/env bash
# Pass-through wrapper for docker compose with strip override + dev overrides
# Usage: ./dc-with-dev.sh ps, ./dc-with-dev.sh logs frost, etc.

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

docker compose \
    -f "${DIR_SCRIPT}/docker-compose.yml" \
    -f "${DIR_SCRIPT}/docker-compose-water-dp.yml" \
    -f "${DIR_SCRIPT}/docker-compose-dev.yml" \
    "$@"