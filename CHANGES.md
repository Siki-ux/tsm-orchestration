# What Changed and Why

This document covers the major architectural additions made to `tsm-orchestration`. The existing README describes how to run the stack; this document explains the *motivation and design* behind each significant new piece.

---

## 1. Water Data Platform Integration

### What it is

`water_dp-api` (a separate repository) runs alongside TSM and shares the same PostgreSQL instance. `tsm-orchestration` gained the infrastructure to host it.

### What was added

- **`docker-compose-water-dp.yml`** — a compose overlay that adds the `water-dp-api` service, a Redis instance, and a Celery worker to the TSM stack, all sharing the existing TSM database container and internal network (`water_shared_net`).
- **`src/sql/water_dp/`** — SQL schema deployed into the shared Postgres database under the `water_dp` schema. Tables: `projects`, `project_sensors`, `alerts`, `alert_definitions`, `computation_scripts`, `computation_jobs`, `simulations`, `dashboards`. Deployed by running `000_deploy_all.sql`.
- **`docs/water_dp_integration.md`** — step-by-step guide for starting the integrated stack.

### Why

Keeping the application schema inside the TSM database avoids running a second Postgres instance and gives `water_dp-api` direct access to the per-thing TimeIO schemas (e.g. `user_abc123`) without cross-server queries. See [`docs/water_dp_integration.md`](docs/water_dp_integration.md) for deployment steps.

---

## 2. Podman Support

### What it is

An alternative runtime path so the stack can run under rootless Podman instead of Docker.

### What was added

- **`up.sh --podman` flag** — generates `docker-compose.podman.yml` and `nginx/tsm.local.podman.conf` at runtime via `sed` transforms, then invokes `podman compose`.
- **`strip_depends.py`** — removes `init` and `flyway` from `depends_on` blocks in the generated compose file, then starts those containers manually and waits for them to exit before launching the rest of the stack.
- **`docker-compose.override.podman.yml`** — tuning overrides for Podman: `userns_mode: keep-id`, healthcheck timing adjustments.
- **`nginx/tsm.local.conf`** — the canonical local nginx config (port 80). The Podman variant (`tsm.local.podman.conf`) is generated from this at runtime by substituting port 80 → 8080.

> **Note:** `docker-compose.podman.yml` and `nginx/tsm.local.podman.conf` are generated files — do not commit them.

### Why Podman is needed

Rootless Podman is required on some HPC and institutional Linux hosts that do not permit the Docker daemon or require auditability of container runtime privileges.

### Why port 8080 for Podman

Unprivileged (rootless) containers cannot bind port 80 without a kernel sysctl override (`net.ipv4.ip_unprivileged_port_start=80`). Port 8080 is used by default so the stack starts without root access.

### Why `strip_depends.py` is needed

`podman-compose` does not cleanly handle short-lived dependency containers (`init`, `flyway`) inside `depends_on` — it either hangs waiting for them or errors on their exit codes. The script removes those dependencies; `up.sh` then starts the short-lived containers manually and calls `podman wait` before proceeding.

### `up.sh` flag reference

| Flag | Behaviour |
|---|---|
| *(none)* | TSM base services + `docker-compose-water-dp.yml` overlay |
| `--base` | TSM core services only (no water\_dp overlay) |
| `--full` | All TSM services, no stripping, no water\_dp overlay |
| `--tunnel` | Same as default but also starts a `cloudflared` tunnel container |
| `--podman` | Combine with any of the above to use Podman runtime |

---

## 3. STA Views Local (`src/sql/sta_views_local/`)

### What it is

Nine SQL view definitions — one per SensorThings API entity — that implement the FROST server's database interface against local TSM schemas instead of the upstream SMS (Sensor Management System) service.

### Views provided

`Thing`, `Datastream`, `Observation`, `FeatureOfInterest`, `Location`, `ObservedProperty`, `Sensor`, `HistoricalLocation`, `ThingsLocations`.

### Why

The upstream UFZ SMS service was not available in this deployment. FROST requires a specific database view interface; these local views satisfy that interface using the per-thing schemas (`user_*`) that TSM already maintains. Controlled by the `USE_LOCAL_STA_VIEWS=true` environment variable in `.env` — the worker reads this flag before deciding which SQL to apply.

This is a **temporary arrangement**. When the upstream SMS is available, set `USE_LOCAL_STA_VIEWS=false` and rebuild the `worker-thing-setup` container.

---

## 4. Grafana Views (`src/sql/grafana_views_local/`)

Denormalized views exposing aggregated time series data in a shape that Grafana's native PostgreSQL datasource can query directly (no joins required). These complement the STA views: STA views serve FROST/API consumers; Grafana views serve the visualization layer.

---

## 5. Docker Compose Restructuring

The base `docker-compose.yml` is now a clean definition of TSM core services only. Environment-specific concerns are layered in via overlays:

| File | Purpose |
|---|---|
| `docker-compose.yml` | Core TSM services (database, MQTT, FROST, MinIO, Keycloak, etc.) |
| `docker-compose-water-dp.yml` | Adds water-dp-api, Redis, Celery worker |
| `docker-compose.override.yml` | Local developer defaults (auto-merged by Docker Compose) |
| `docker-compose.override.podman.yml` | Podman-specific tunables |

### Why

The previous flat structure made it impossible to run subsets of services. The overlay pattern follows Docker Compose best practices and lets `up.sh` assemble the right set of files for each mode without maintaining multiple full copies of the compose definition.

---

## 6. Nginx Restructuring

| File | Purpose |
|---|---|
| `nginx/tsm.local.conf` | Local development — HTTP, port 80 |
| `nginx/tsm.local.podman.conf` | Generated at runtime by `up.sh --podman` — port 8080 |
| `nginx/tsm.tls.conf` | Production — HTTPS with TLS termination (unchanged) |
| `nginx/locations/locations.conf` | Upstream proxy rules (shared by all configs) |

Previously the nginx config was mixed with deployment concerns. Separating local / Podman / production configs makes the proxy configuration auditable and prevents accidental port or certificate mismatches between environments.

---

## 7. Flyway Migrations V2_27 – V2_29

| Migration | What it does | Why |
|---|---|---|
| `V2_27__add_properties_to_mqtt_device_type.sql` | Adds a `properties` JSON column to `mqtt_device_type` | Allows device-type-level metadata (e.g. expected units, topic patterns) without a schema change per new device type |
| `V2_28__drop_s3_store_parser_unique_constraint.sql` | Drops a unique constraint on the `s3_store_parser` table | The constraint was preventing valid configurations where one S3 source feeds multiple parsers |
| `V2_29__add_properties_to_ext_api_type.sql` | Adds `properties` JSON column to `ext_api_type` | Same reason as V2_27 — allows per-type metadata for external API sources |

---

## 8. Environment Configuration (`env.example2`)

`env.example2` is a 1,237-line annotated environment variable reference. It is **not** an operational template — it exists purely as documentation.

Each variable is tagged:
- `@service` — which Docker service reads it
- `@security` — marks credentials and secrets
- `@choices` — valid values for enum-style variables
- `@dev` — the recommended development default
- `@dependant` — notes variables whose values depend on others

**Operational workflow:** copy `.env.example` to `.env` and fill in values. Use `env.example2` to understand what each variable does.

---

## 9. GitLab CI/CD Removed

The 12 GitLab CI/CD configuration files (`.gitlab/ci/`, `.gitlab/merge_request_templates/`) were deleted. This deployment no longer uses GitLab pipelines. CI/CD is now managed via GitHub Actions in the `water_dp-api` repository, or externally.

---

## 10. Python Source Updates

| File | What changed | Why |
|---|---|---|
| `src/timeio/parser/dynamic_loader.py` | Parsers now resolved by UUID in addition to integer ID | Integer IDs are not stable across restarts when parsers are re-registered; UUIDs provide a stable identifier |
| `src/timeio/ext_api.py` | Updated payload structure | External API endpoint contract changed; old payload format was rejected |
| `src/setup_user_database.py` | STA views deployment is now conditional | Reads `USE_LOCAL_STA_VIEWS` from env before deciding which SQL to apply; previously always applied upstream views |
| `src/sync_extapi_manager.py` | Fixed stalling sync; handles new `ext_api_type.properties` field | Sync would hang indefinitely on certain error responses; now times out and retries correctly |

---

## 11. Keycloak Template Updates

`keycloak/keycloak-init.template.json` was extended to configure group-based authorization. The same Keycloak realm now issues tokens that `water_dp-api` validates for group membership — the user's Keycloak groups determine which water\_dp projects they can access. No separate realm or client is needed for `water_dp-api`.
