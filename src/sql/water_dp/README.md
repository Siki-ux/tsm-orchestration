# water_dp Schema

Database schema for the Water Data Platform, integrated into tsm-orchestration.

## Overview

The `water_dp` schema provides:
- **Project management** - Group sensors, dashboards, and computations
- **Alert system** - Define rules and track triggered alerts
- **Computation engine** - User-uploaded scripts for data processing
- **Simulation tools** - Generate test data for development
- **GeoServer integration** - Link projects to GeoServer layers (future)

## Deployment

### Deploy all tables

```bash
# From tsm-orchestration directory
docker-compose exec -T database psql -U postgres -d postgres -f /app/src/sql/water_dp/000_deploy_all.sql
```

Or deploy individually:

```bash
docker-compose exec -T database psql -U postgres -d postgres -f /app/src/sql/water_dp/001_core_tables.sql
docker-compose exec -T database psql -U postgres -d postgres -f /app/src/sql/water_dp/002_alerts.sql
# ... etc
```

## File Structure

| File | Description |
|------|-------------|
| `000_deploy_all.sql` | Master script - runs all DDL files |
| `001_core_tables.sql` | projects, project_sensors, project_members, dashboards |
| `002_alerts.sql` | alert_definitions, alerts |
| `003_computations.sql` | computation_scripts, computation_jobs |
| `004_simulations.sql` | simulations |
| `005_geo_layers.sql` | project_geo_layers (future GeoServer link) |
| `010_views.sql` | Comprehensive views |

## Tables

### Core Tables

- **projects** - User projects with TimeIO schema linkage
- **project_sensors** - Links projects to TimeIO things (via `thing_uuid`)
- **project_members** - Role-based access control (viewer, editor, admin)
- **dashboards** - Dashboard configurations (layout, widgets)

### Alert Tables

- **alert_definitions** - Alert rules (threshold, nodata, computation_failure)
- **alerts** - Triggered alert instances with lifecycle (active → acknowledged → resolved)

### Computation Tables

- **computation_scripts** - User-uploaded Python scripts
- **computation_jobs** - Job execution tracking (Celery task IDs)

### Other Tables

- **simulations** - Simulated data generators for testing
- **project_geo_layers** - Future GeoServer layer associations

## Views

| View | Description |
|------|-------------|
| `v_project_overview` | Project summary with entity counts |
| `v_project_sensors_detail` | Sensors with project metadata |
| `v_active_alerts` | Active alerts ordered by severity |
| `v_computation_jobs_status` | Job status with duration |
| `v_simulation_status` | Simulation health with staleness detection |

## TimeIO Integration

The schema connects to TimeIO via:

1. **`projects.schema_name`** → TimeIO project schema (e.g., `my_project`)
2. **`project_sensors.thing_uuid`** → UUID of TimeIO thing (matches `thing.uuid`)
3. **`simulations.thing_uuid`** → UUID of TimeIO thing to simulate

## Example Queries

```sql
-- Get all sensors in a project with thing details
SELECT ps.thing_uuid, p.name, p.schema_name
FROM water_dp.project_sensors ps
JOIN water_dp.projects p ON ps.project_id = p.id
WHERE p.id = 'your-project-uuid';

-- Get active alerts for a project owner
SELECT * FROM water_dp.v_active_alerts
WHERE project_owner = 'keycloak-user-id';

-- Check simulation health
SELECT * FROM water_dp.v_simulation_status
WHERE is_stale = TRUE;
```
