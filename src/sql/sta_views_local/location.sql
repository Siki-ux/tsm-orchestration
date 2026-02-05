-- TSM-TEMP-DISABLED: Local FROST view for LOCATIONS (replaces SMS-based view)
-- This view extracts location from thing.properties JSON instead of SMS tables
-- To revert: Delete this file and set USE_LOCAL_STA_VIEWS=false
--
-- Thing properties should include location like:
-- {"latitude": 51.3397, "longitude": 12.3731, "locationName": "Leipzig"}

DROP VIEW IF EXISTS "LOCATIONS" CASCADE;
CREATE VIEW "LOCATIONS" AS
SELECT
    t.id AS "ID",
    t.name AS "NAME",
    'Location of ' || t.name AS "DESCRIPTION",
    'application/vnd.geo+json'::varchar AS "ENCODING_TYPE",
    -- Extract GeoJSON Location Object
    COALESCE(
        CASE 
            WHEN jsonb_typeof(t.properties) = 'array' AND jsonb_array_length(t.properties) > 1 THEN t.properties->1->'location'
            ELSE t.properties->'location'
        END,
        '{"type": "Point", "coordinates": [0,0]}'::jsonb
    ) AS "LOCATION",
    -- Extract Properties
    CASE 
        WHEN jsonb_typeof(t.properties) = 'object' THEN t.properties
        WHEN jsonb_typeof(t.properties) = 'array' AND jsonb_array_length(t.properties) > 1 THEN t.properties->1
        WHEN t.properties IS NULL THEN '{}'::jsonb
        ELSE jsonb_build_object('wrapped_value', t.properties)
    END AS "PROPERTIES",
    -- Create Geometry (PostGIS)
    public.ST_GeomFromGeoJSON(
        COALESCE(
            CASE 
                WHEN jsonb_typeof(t.properties) = 'array' AND jsonb_array_length(t.properties) > 1 THEN t.properties->1->'location'
                ELSE t.properties->'location'
            END,
            '{"type": "Point", "coordinates": [0,0]}'::jsonb
        )::text
    ) AS "GEOM"
FROM thing t
ORDER BY t.id ASC;

-- View to link things to their locations (for local data, each thing IS its location)
DROP VIEW IF EXISTS "THINGS_LOCATIONS" CASCADE;
CREATE VIEW "THINGS_LOCATIONS" AS
SELECT
    t.id AS "THING_ID",
    t.id AS "LOCATION_ID"  -- In local mode, thing ID = location ID
FROM thing t
WHERE t.properties->>'longitude' IS NOT NULL 
  AND t.properties->>'latitude' IS NOT NULL
ORDER BY t.id ASC;
