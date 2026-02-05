-- ============================================
-- water_dp Schema DDL
-- Part 4: Simulations Table
-- ============================================

-- ============================================
-- SIMULATIONS
-- Simulated data generators for testing/demo
-- ============================================
CREATE TABLE water_dp.simulations (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    thing_uuid      uuid        NOT NULL UNIQUE,  -- TimeIO thing UUID
    
    -- Configuration for simulated datastreams
    -- Format: [{"name": "temperature", "pattern": "sine", "min": 10, "max": 30, "period": 3600}, ...]
    config          jsonb       NOT NULL,
    
    is_enabled      boolean     NOT NULL DEFAULT TRUE,
    
    -- Execution tracking
    last_run        timestamptz,
    interval_seconds integer    NOT NULL DEFAULT 60,
    
    created_at      timestamptz NOT NULL DEFAULT NOW(),
    updated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_simulations_thing ON water_dp.simulations(thing_uuid);
CREATE INDEX idx_simulations_enabled ON water_dp.simulations(is_enabled) WHERE is_enabled = TRUE;

COMMENT ON TABLE water_dp.simulations IS 'Simulated data generators for testing and demonstrations';
COMMENT ON COLUMN water_dp.simulations.thing_uuid IS 'TimeIO thing to simulate data for';
COMMENT ON COLUMN water_dp.simulations.config IS 'JSON array of datastream simulation configurations';
COMMENT ON COLUMN water_dp.simulations.interval_seconds IS 'Interval between simulated data points';
