-- ============================================
-- water_dp Schema DDL
-- Part 5: Future GeoServer Integration
-- ============================================

-- ============================================
-- PROJECT GEO LAYERS
-- Simple association for linking GeoServer layers to projects
-- GeoServer manages the actual layer data in its own schema
-- ============================================
CREATE TABLE water_dp.project_geo_layers (
    project_id  uuid        NOT NULL REFERENCES water_dp.projects(id) ON DELETE CASCADE,
    layer_name  varchar(255) NOT NULL,  -- GeoServer layer name
    workspace   varchar(100) DEFAULT 'water_data',  -- GeoServer workspace
    
    -- Optional metadata
    display_name varchar(255),
    description  text,
    layer_type   varchar(50),  -- vector, raster, wms, wfs
    
    added_at    timestamptz DEFAULT NOW(),
    
    PRIMARY KEY (project_id, layer_name)
);

CREATE INDEX idx_project_geo_layers_layer ON water_dp.project_geo_layers(layer_name);

COMMENT ON TABLE water_dp.project_geo_layers IS 'Links water_dp projects to GeoServer layers';
COMMENT ON COLUMN water_dp.project_geo_layers.layer_name IS 'GeoServer layer name (managed by GeoServer)';
COMMENT ON COLUMN water_dp.project_geo_layers.workspace IS 'GeoServer workspace containing the layer';
