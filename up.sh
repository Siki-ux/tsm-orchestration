#!/usr/bin/env bash
# Start all TSM services (stripped for water_dp)
# Usage:
#   ./up.sh           - Start TSM + water_dp services (default)
#   ./up.sh --base    - Start base TSM services only (no water_dp)
#   ./up.sh --full    - Start ALL TSM services (no strip, no water_dp)
#   ./up.sh --tunnel  - Also start cloudflared (Cloudflare Tunnel) alongside water_dp

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PODMAN_MODE=false
TARGET_MODE=""
TUNNEL_MODE=false

for arg in "$@"; do
    if [[ "$arg" == "--podman" ]]; then
        PODMAN_MODE=true
    elif [[ "$arg" == "--full" || "$arg" == "--base" ]]; then
        TARGET_MODE="$arg"
    elif [[ "$arg" == "--tunnel" ]]; then
        TUNNEL_MODE=true
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
    
    # 1) Generate Podman-specific Nginx config to run on unprivileged port 8080
    if [ -f "${DIR_SCRIPT}/nginx/tsm.local.conf" ]; then
        sed -e 's/listen       80;/listen       8080;/g' \
            -e 's/listen  \[::\]:80;/listen  \[::\]:8080;/g' \
            "${DIR_SCRIPT}/nginx/tsm.local.conf" > "${DIR_SCRIPT}/nginx/tsm.local.podman.conf"
    fi

    # 2) Generate Podman-specific compose file directly from base, quoting "restart: no" and fixing tmpfs/ports
    sed -e 's/restart: no$/restart: "no"/' \
        -e 's|/var/lib/mosquitto/:uid=${UID}|/var/lib/mosquitto/:mode=1777|' \
        -e 's|"${OBJECT_STORAGE_SFTP_PORT}:22"|"${OBJECT_STORAGE_SFTP_PORT}:2022"|' \
        -e 's|"${OBJECT_STORAGE_FTP_PORT}:21"|"${OBJECT_STORAGE_FTP_PORT}:2021"|' \
        -e 's|--ftp address=:21|--ftp address=:2021|' \
        -e 's|--sftp address=:22|--sftp address=:2022|' \
        -e 's|"${PROXY_PLAIN_PORT_MAPPING}"|"${PROXY_HOST}:80:8080"|' \
        -e 's#curl -f http://localhost:80 || exit 1#curl -f http://localhost:8080 || exit 1#' \
        -e 's|nginx/${PROXY_SITE_CONFIG_FILE}|nginx/tsm.local.podman.conf|' \
        "${DIR_SCRIPT}/docker-compose.yml" > "${DIR_SCRIPT}/docker-compose.podman.yml"
    
    # 3) Strip 'init' and 'flyway' from depends_on blocks to prevent podman-compose hang
    python3 "${DIR_SCRIPT}/strip_depends.py" "${DIR_SCRIPT}/docker-compose.podman.yml"

    # --in-pod false prevents conflict between userns_mode: keep-id and pod networking
    # -p sets project name so containers are named tsm-orchestration_* consistently
    # use `env UID=$(id -u)` to bypass bash's readonly restriction and pass UID correctly
    COMPOSE_CMD="env UID=$(id -u) podman compose --in-pod false -p tsm-orchestration"
    # UID is a bash built-in (readonly), no need to export.
    # Only export GID which is not set by default.
    export GID=$(id -g)
    # Use podman-specific compose file + podman overrides (healthcheck tuning, userns_mode, etc.)
    COMPOSE_BASE="-f ${DIR_SCRIPT}/docker-compose.podman.yml -f ${DIR_SCRIPT}/docker-compose.override.podman.yml"

    # 3) Short-lived containers need to start and finish FIRST because we stripped their deps
    echo "Starting 'init' container (waiting for completion)..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d init
    podman wait tsm-orchestration_init_1
    
    # Fix visualization (Grafana) volume ownership.
    # init.sh runs chown inside a container WITHOUT userns_mode:keep-id, so UID 1000 inside
    # that container maps to a subUID on the host — NOT the real host UID. The visualization
    # container uses userns_mode:keep-id, so it runs as the actual host UID and needs to own
    # the volume files on the host filesystem.
    # Must use `podman unshare` because the files are owned by subUIDs inaccessible from the host.
    # Inside `podman unshare`, UID 0 = the real host user, so chown -R 0:0 restores correct ownership.
    VIZ_VOL=$(podman volume inspect tsm-orchestration_visualization --format '{{.Mountpoint}}' 2>/dev/null)
    if [[ -n "$VIZ_VOL" ]]; then
        echo "Fixing Grafana volume ownership: podman unshare chown 0:0 $VIZ_VOL"
        podman unshare chown -R 0:0 "$VIZ_VOL"
    fi

    echo "Starting 'database' and 'flyway' (waiting for migrations to complete)..."
    # flyway's depends_on: database is preserved, so 'up flyway' will bring up db and wait for health
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d flyway
    podman wait tsm-orchestration_flyway_1
fi

COMPOSE_WATER="-f ${DIR_SCRIPT}/docker-compose-water-dp.yml"

if [[ "$TARGET_MODE" == "--full" ]]; then
    echo "Starting ALL TSM services (unstripped, no water_dp)..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d
elif [[ "$TARGET_MODE" == "--base" ]]; then
    echo "Starting stripped TSM services only (no water_dp)..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} up -d
else
    COMPOSE_TUNNEL=""
    if [[ "$TUNNEL_MODE" == "true" ]]; then
        COMPOSE_TUNNEL="-f ${DIR_SCRIPT}/docker-compose.cloudflare.yml"
    fi
    echo "Starting TSM + water_dp services..."
    ${COMPOSE_CMD} ${COMPOSE_BASE} ${COMPOSE_WATER} ${COMPOSE_TUNNEL} up -d
fi