-- ============================================
-- water_dp Schema Setup
-- Master script to deploy all water_dp tables
-- Run this script to create the complete schema
-- ============================================

-- Usage:
-- psql -U postgres -d postgres -f src/sql/water_dp/000_deploy_all.sql
-- OR
-- docker-compose exec -T database psql -U postgres -d postgres -f /path/to/000_deploy_all.sql

\echo 'Creating water_dp schema...'

-- Include all DDL files in order
\ir 001_core_tables.sql
\echo '✓ Core tables created'

\ir 002_alerts.sql
\echo '✓ Alert tables created'

\ir 003_computations.sql
\echo '✓ Computation tables created'

\ir 004_simulations.sql
\echo '✓ Simulations table created'

\ir 005_geo_layers.sql
\echo '✓ Geo layers association table created'

\ir 010_views.sql
\echo '✓ Views created'

\echo ''
\echo '=========================================='
\echo 'water_dp schema deployment complete!'
\echo '=========================================='
\echo ''
\echo 'Tables created:'
\echo '  - water_dp.projects'
\echo '  - water_dp.project_sensors'
\echo '  - water_dp.project_members'
\echo '  - water_dp.dashboards'
\echo '  - water_dp.alert_definitions'
\echo '  - water_dp.alerts'
\echo '  - water_dp.computation_scripts'
\echo '  - water_dp.computation_jobs'
\echo '  - water_dp.simulations'
\echo '  - water_dp.project_geo_layers'
\echo ''
\echo 'Views created:'
\echo '  - water_dp.v_project_overview'
\echo '  - water_dp.v_project_sensors_detail'
\echo '  - water_dp.v_active_alerts'
\echo '  - water_dp.v_computation_jobs_status'
\echo '  - water_dp.v_simulation_status'
