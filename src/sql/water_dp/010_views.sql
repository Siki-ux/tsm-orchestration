-- ============================================
-- water_dp Schema Views
-- Comprehensive views joining water_dp with TimeIO data
-- ============================================

-- ============================================
-- PROJECT OVERVIEW
-- Summary view with counts
-- ============================================
CREATE OR REPLACE VIEW water_dp.v_project_overview AS
SELECT 
    p.id,
    p.name,
    p.description,
    p.owner_id,
    p.schema_name,
    p.authorization_provider_group_id,
    p.properties,
    p.created_at,
    p.updated_at,
    (SELECT COUNT(*) FROM water_dp.project_sensors ps WHERE ps.project_id = p.id) AS sensor_count,
    (SELECT COUNT(*) FROM water_dp.dashboards d WHERE d.project_id = p.id) AS dashboard_count,
    (SELECT COUNT(*) FROM water_dp.alert_definitions ad WHERE ad.project_id = p.id AND ad.is_active) AS active_alert_def_count,
    (SELECT COUNT(*) FROM water_dp.project_members pm WHERE pm.project_id = p.id) AS member_count,
    (SELECT COUNT(*) FROM water_dp.computation_scripts cs WHERE cs.project_id = p.id) AS script_count
FROM water_dp.projects p;

COMMENT ON VIEW water_dp.v_project_overview IS 'Project summary with entity counts';


-- ============================================
-- PROJECT SENSORS DETAIL
-- Sensor details with project info
-- ============================================
CREATE OR REPLACE VIEW water_dp.v_project_sensors_detail AS
SELECT 
    ps.project_id,
    p.name AS project_name,
    p.schema_name,
    p.owner_id AS project_owner,
    ps.thing_uuid,
    ps.added_at
FROM water_dp.project_sensors ps
JOIN water_dp.projects p ON ps.project_id = p.id;

COMMENT ON VIEW water_dp.v_project_sensors_detail IS 'Project sensors with project metadata';


-- ============================================
-- ACTIVE ALERTS
-- Currently active alerts with definition details
-- ============================================
CREATE OR REPLACE VIEW water_dp.v_active_alerts AS
SELECT 
    a.id AS alert_id,
    a.timestamp,
    a.message,
    a.details,
    a.status,
    a.created_at,
    ad.id AS definition_id,
    ad.name AS alert_name,
    ad.severity,
    ad.alert_type,
    ad.target_id,
    ad.conditions,
    p.id AS project_id,
    p.name AS project_name,
    p.owner_id AS project_owner
FROM water_dp.alerts a
JOIN water_dp.alert_definitions ad ON a.definition_id = ad.id
JOIN water_dp.projects p ON ad.project_id = p.id
WHERE a.status = 'active'
ORDER BY 
    CASE ad.severity 
        WHEN 'critical' THEN 1 
        WHEN 'warning' THEN 2 
        ELSE 3 
    END,
    a.timestamp DESC;

COMMENT ON VIEW water_dp.v_active_alerts IS 'Active alerts ordered by severity and time';


-- ============================================
-- COMPUTATION JOBS STATUS
-- Recent computation jobs with script info
-- ============================================
CREATE OR REPLACE VIEW water_dp.v_computation_jobs_status AS
SELECT 
    cj.id AS job_id,
    cj.status,
    cj.start_time,
    cj.end_time,
    cj.created_at,
    EXTRACT(EPOCH FROM (COALESCE(cj.end_time, NOW()) - cj.start_time)) AS duration_seconds,
    cs.id AS script_id,
    cs.name AS script_name,
    cs.filename,
    cj.user_id,
    p.id AS project_id,
    p.name AS project_name,
    cj.error IS NOT NULL AS has_error
FROM water_dp.computation_jobs cj
JOIN water_dp.computation_scripts cs ON cj.script_id = cs.id
JOIN water_dp.projects p ON cs.project_id = p.id
ORDER BY cj.created_at DESC;

COMMENT ON VIEW water_dp.v_computation_jobs_status IS 'Computation job status with script and project info';


-- ============================================
-- SIMULATION STATUS
-- Active simulations with timing info
-- ============================================
CREATE OR REPLACE VIEW water_dp.v_simulation_status AS
SELECT 
    s.id,
    s.thing_uuid,
    s.is_enabled,
    s.interval_seconds,
    s.last_run,
    s.config,
    NOW() - s.last_run AS time_since_last_run,
    CASE 
        WHEN s.is_enabled AND s.last_run IS NOT NULL 
             AND (NOW() - s.last_run) > (s.interval_seconds * 2 || ' seconds')::interval
        THEN TRUE 
        ELSE FALSE 
    END AS is_stale
FROM water_dp.simulations s;

COMMENT ON VIEW water_dp.v_simulation_status IS 'Simulation status with staleness detection';
