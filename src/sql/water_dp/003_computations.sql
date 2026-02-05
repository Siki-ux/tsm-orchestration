-- ============================================
-- water_dp Schema DDL
-- Part 3: Computation Tables
-- ============================================

-- ============================================
-- COMPUTATION SCRIPTS
-- User-uploaded Python scripts for data processing
-- ============================================
CREATE TABLE water_dp.computation_scripts (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid        NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    name            varchar(255) NOT NULL,
    description     text,
    filename        varchar(255) NOT NULL,  -- Original filename
    
    -- Script storage (could be file path or inline)
    script_content  text,        -- Optional: inline script storage
    storage_path    varchar(500), -- Optional: path to script file
    
    uploaded_by     varchar(255) NOT NULL,  -- Keycloak user ID
    
    created_at      timestamptz NOT NULL DEFAULT NOW(),
    updated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comp_scripts_project ON water_dp.computation_scripts(project_id);
CREATE INDEX idx_comp_scripts_uploader ON water_dp.computation_scripts(uploaded_by);

COMMENT ON TABLE water_dp.computation_scripts IS 'User-uploaded computation scripts for data processing';
COMMENT ON COLUMN water_dp.computation_scripts.filename IS 'Original filename of the uploaded script';
COMMENT ON COLUMN water_dp.computation_scripts.script_content IS 'Inline script content (alternative to file storage)';


-- ============================================
-- COMPUTATION JOBS
-- Execution tracking for computation scripts
-- ============================================
CREATE TABLE water_dp.computation_jobs (
    id          varchar(255) PRIMARY KEY,  -- Celery/task queue task ID
    script_id   uuid        NOT NULL REFERENCES water_dp.computation_scripts(id) ON DELETE CASCADE,
    user_id     varchar(255) NOT NULL,     -- User who started the job
    
    -- Execution status
    status      varchar(50) NOT NULL DEFAULT 'PENDING',  -- PENDING, RUNNING, SUCCESS, FAILURE, REVOKED
    
    -- Timing
    start_time  timestamptz,
    end_time    timestamptz,
    
    -- Results
    result      jsonb,      -- Job output/result data
    error       text,       -- Error message if failed
    logs        text,       -- Console output / logs
    
    -- Input parameters
    input_params jsonb,     -- Parameters passed to the script
    
    created_at  timestamptz NOT NULL DEFAULT NOW(),
    updated_at  timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comp_jobs_script ON water_dp.computation_jobs(script_id);
CREATE INDEX idx_comp_jobs_user ON water_dp.computation_jobs(user_id);
CREATE INDEX idx_comp_jobs_status ON water_dp.computation_jobs(status);
CREATE INDEX idx_comp_jobs_created ON water_dp.computation_jobs(created_at DESC);

COMMENT ON TABLE water_dp.computation_jobs IS 'Computation job execution tracking';
COMMENT ON COLUMN water_dp.computation_jobs.id IS 'Celery/task queue task ID';
COMMENT ON COLUMN water_dp.computation_jobs.status IS 'Job status: PENDING, RUNNING, SUCCESS, FAILURE, REVOKED';
