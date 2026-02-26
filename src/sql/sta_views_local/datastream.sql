-- TSM-TEMP-DISABLED: Local FROST view for DATASTREAMS (replaces SMS-based view)
-- This view queries local 'datastream' table instead of public.sms_* tables
-- To revert: Delete this file and set USE_LOCAL_STA_VIEWS=false
--
-- UNIT_OF_MEASUREMENT can be set via datastream.properties JSON:
-- {"unit_name": "Celsius", "unit_symbol": "°C", "unit_definition": "http://qudt.org/vocab/unit/DEG_C"}

DROP VIEW IF EXISTS "DATASTREAMS" CASCADE;
CREATE VIEW "DATASTREAMS" AS
SELECT
    d.id AS "ID",
    COALESCE(
        (CASE 
            WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'label'
            ELSE d.properties->>'label'
        END), d.name) AS "NAME",
    COALESCE(d.description, d.name) AS "DESCRIPTION",
    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement' AS "OBSERVATION_TYPE",
    CASE 
        WHEN jsonb_typeof(d.properties) = 'object' THEN d.properties
        WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1
        WHEN d.properties IS NULL THEN '{}'::jsonb
        ELSE jsonb_build_object('wrapped_value', d.properties)
    END AS "PROPERTIES",
    -- Flat Unit Columns (Required by FROST Persistence)
    COALESCE(
        (CASE 
            WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_name'
            ELSE d.properties->>'unit_name'
        END), d.position, '') AS "UNIT_NAME",
    COALESCE(
        (CASE 
            WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_symbol'
            ELSE d.properties->>'unit_symbol'
        END), '') AS "UNIT_SYMBOL",
    COALESCE(
        (CASE 
            WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_definition'
            ELSE d.properties->>'unit_definition'
        END), '') AS "UNIT_DEFINITION",
    -- Unit of Measurement JSON (Required by FROST API)
    jsonb_build_object(
        'name', COALESCE(
            (CASE 
                WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_name'
                ELSE d.properties->>'unit_name'
            END), d.position, ''),
        'symbol', COALESCE(
            (CASE 
                WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_symbol'
                ELSE d.properties->>'unit_symbol'
            END), ''),
        'definition', COALESCE(
            (CASE 
                WHEN jsonb_typeof(d.properties) = 'array' AND jsonb_array_length(d.properties) > 1 THEN d.properties->1->>'unit_definition'
                ELSE d.properties->>'unit_definition'
            END), '')
    ) AS "UNIT_OF_MEASUREMENT",
    public.ST_GeomFromText('POLYGON EMPTY') AS "OBSERVED_AREA",
    NULL::timestamptz AS "PHENOMENON_TIME_START",
    NULL::timestamptz AS "PHENOMENON_TIME_END",
    NULL::timestamptz AS "RESULT_TIME_START",
    NULL::timestamptz AS "RESULT_TIME_END",
    d.thing_id AS "THING_ID",
    NULL::bigint AS "SENSOR_ID",
    NULL::bigint AS "OBS_PROPERTY_ID"
FROM datastream d
ORDER BY d.id ASC;
