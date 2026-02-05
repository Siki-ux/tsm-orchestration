-- ============================================
-- water_dp Schema DDL
-- Part 2: Alerts Tables
-- ============================================

-- ============================================
-- ALERT DEFINITIONS
-- Rules for triggering alerts based on conditions
-- ============================================
CREATE TABLE water_dp.alert_definitions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid        NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    name            varchar(255) NOT NULL,
    description     text,
    
    -- Alert configuration
    alert_type      varchar(50) NOT NULL,  -- threshold, nodata, computation_failure, computation_result
    target_id       varchar(255),          -- thing_uuid, datastream position, or computation script ID
    
    -- Conditions stored as JSON for flexibility
    -- Examples:
    --   {"operator": ">", "value": 50.0}
    --   {"duration_minutes": 60, "condition": "no_data"}
    conditions      jsonb       NOT NULL DEFAULT '{}',
    
    is_active       boolean     NOT NULL DEFAULT TRUE,
    severity        varchar(20) NOT NULL DEFAULT 'warning',  -- info, warning, critical
    
    created_at      timestamptz NOT NULL DEFAULT NOW(),
    updated_at      timestamptz NOT NULL DEFAULT NOW(),
    created_by      varchar(100)
);

CREATE INDEX idx_alert_defs_project ON water_dp.alert_definitions(project_id);
CREATE INDEX idx_alert_defs_active ON water_dp.alert_definitions(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_alert_defs_type ON water_dp.alert_definitions(alert_type);

COMMENT ON TABLE water_dp.alert_definitions IS 'Alert rule definitions for monitoring sensor data';
COMMENT ON COLUMN water_dp.alert_definitions.alert_type IS 'Type: threshold, nodata, computation_failure, computation_result';
COMMENT ON COLUMN water_dp.alert_definitions.target_id IS 'Target entity: thing UUID, datastream position, or script ID';
COMMENT ON COLUMN water_dp.alert_definitions.conditions IS 'JSON conditions for alert triggering';


-- ============================================
-- ALERTS
-- Triggered alert instances
-- ============================================
CREATE TABLE water_dp.alerts (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   uuid        NOT NULL REFERENCES water_dp.alert_definitions(id) ON DELETE CASCADE,
    
    timestamp       timestamptz NOT NULL DEFAULT NOW(),
    status          varchar(20) NOT NULL DEFAULT 'active',  -- active, acknowledged, resolved
    
    message         text        NOT NULL,
    details         jsonb,  -- Snapshot of triggering value, context, etc.
    
    acknowledged_by varchar(255),
    acknowledged_at timestamptz,
    resolved_at     timestamptz,
    
    created_at      timestamptz NOT NULL DEFAULT NOW(),
    updated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_definition ON water_dp.alerts(definition_id);
CREATE INDEX idx_alerts_status ON water_dp.alerts(status);
CREATE INDEX idx_alerts_timestamp ON water_dp.alerts(timestamp DESC);
CREATE INDEX idx_alerts_active ON water_dp.alerts(status) WHERE status = 'active';

COMMENT ON TABLE water_dp.alerts IS 'Triggered alert instances';
COMMENT ON COLUMN water_dp.alerts.status IS 'Alert lifecycle: active, acknowledged, resolved';
COMMENT ON COLUMN water_dp.alerts.details IS 'JSON snapshot of the triggering data';
