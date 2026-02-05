-- ============================================
-- water_dp Schema DDL
-- Part 1: Core Tables (projects, members, sensors, dashboards)
-- ============================================

-- Create schema
CREATE SCHEMA IF NOT EXISTS water_dp;

-- ============================================
-- PROJECTS
-- Central entity for grouping sensors and dashboards
-- Links to TimeIO via schema_name
-- ============================================
CREATE TABLE water_dp.projects (
    id              uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    name            varchar(255) NOT NULL,
    description     text,
    owner_id        varchar(255) NOT NULL,  -- Keycloak user ID
    properties      jsonb,
    
    -- Keycloak Group for authorization
    authorization_provider_group_id varchar(255),
    
    -- Links to TimeIO project schema (e.g., 'my_project_schema')
    schema_name     varchar(255),
    
    -- Audit fields
    created_at      timestamptz  NOT NULL DEFAULT NOW(),
    updated_at      timestamptz  NOT NULL DEFAULT NOW(),
    created_by      varchar(100),
    updated_by      varchar(100)
);

CREATE INDEX idx_projects_owner ON water_dp.projects(owner_id);
CREATE INDEX idx_projects_schema ON water_dp.projects(schema_name);
CREATE INDEX idx_projects_auth_group ON water_dp.projects(authorization_provider_group_id);

COMMENT ON TABLE water_dp.projects IS 'User projects that group sensors, dashboards, and computations';
COMMENT ON COLUMN water_dp.projects.schema_name IS 'Links to TimeIO project schema for thing/datastream/observation data';
COMMENT ON COLUMN water_dp.projects.owner_id IS 'Keycloak Subject ID of the project owner';


-- ============================================
-- PROJECT SENSORS
-- Association table linking projects to TimeIO things
-- ============================================
CREATE TABLE water_dp.project_sensors (
    project_id  uuid NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    thing_uuid  uuid NOT NULL,  -- TimeIO thing UUID (matches thing.uuid in project schema)
    added_at    timestamptz DEFAULT NOW(),
    
    PRIMARY KEY (project_id, thing_uuid)
);

CREATE INDEX idx_project_sensors_thing ON water_dp.project_sensors(thing_uuid);

COMMENT ON TABLE water_dp.project_sensors IS 'Links water_dp projects to TimeIO things';
COMMENT ON COLUMN water_dp.project_sensors.thing_uuid IS 'UUID of the TimeIO thing (matches thing.uuid in project schema)';


-- ============================================
-- PROJECT MEMBERS
-- Access control for projects
-- ============================================
CREATE TABLE water_dp.project_members (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid        NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    user_id     varchar(255) NOT NULL,  -- Keycloak user ID
    role        varchar(50) NOT NULL DEFAULT 'viewer',  -- viewer, editor, admin
    
    created_at  timestamptz NOT NULL DEFAULT NOW(),
    updated_at  timestamptz NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_project_member UNIQUE (project_id, user_id)
);

CREATE INDEX idx_project_members_user ON water_dp.project_members(user_id);

COMMENT ON TABLE water_dp.project_members IS 'Project membership with role-based access';
COMMENT ON COLUMN water_dp.project_members.role IS 'Access level: viewer, editor, or admin';


-- ============================================
-- DASHBOARDS
-- Dashboard configurations for data visualization
-- ============================================
CREATE TABLE water_dp.dashboards (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid        NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    name            varchar(255) NOT NULL,
    
    layout_config   jsonb,  -- Grid layout positions
    widgets         jsonb,  -- Widget definitions and configurations
    
    is_public       boolean NOT NULL DEFAULT FALSE,
    
    created_at      timestamptz NOT NULL DEFAULT NOW(),
    updated_at      timestamptz NOT NULL DEFAULT NOW(),
    created_by      varchar(100),
    updated_by      varchar(100)
);

CREATE INDEX idx_dashboards_project ON water_dp.dashboards(project_id);
CREATE INDEX idx_dashboards_public ON water_dp.dashboards(is_public) WHERE is_public = TRUE;

COMMENT ON TABLE water_dp.dashboards IS 'Dashboard configurations for visualizing project data';
COMMENT ON COLUMN water_dp.dashboards.layout_config IS 'JSON grid layout for widget positioning';
COMMENT ON COLUMN water_dp.dashboards.widgets IS 'JSON array of widget definitions';
