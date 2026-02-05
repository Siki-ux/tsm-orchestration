-- TSM-TEMP-DISABLED: Local FROST view for OBSERVATIONS (replaces SMS-based view)
-- This view queries local 'observation' table instead of helper views using SMS data
-- To revert: Delete this file and set USE_LOCAL_STA_VIEWS=false

DROP VIEW IF EXISTS "OBSERVATIONS" CASCADE;
CREATE VIEW "OBSERVATIONS" AS
SELECT
    o.id AS "ID",
    o.result_boolean AS "RESULT_BOOLEAN",
    o.result_quality AS "RESULT_QUALITY",
    o.phenomenon_time_start AS "PHENOMENON_TIME_START",
    COALESCE(o.parameters, '{}'::jsonb) AS "PARAMETERS",
    o.datastream_id AS "DATASTREAM_ID",
    o.result_string AS "RESULT_STRING",
    o.result_type AS "RESULT_TYPE",
    o.valid_time_end AS "VALID_TIME_END",
    o.phenomenon_time_end AS "PHENOMENON_TIME_END",
    NULL::bigint AS "FEATURE_ID",
    o.result_json AS "RESULT_JSON",
    o.result_time AS "RESULT_TIME",
    o.result_number AS "RESULT_NUMBER",
    o.valid_time_start AS "VALID_TIME_START",
    jsonb_build_object(
        '@context', jsonb_build_object(
            '@version', '1.1',
            '@vocab', 'http://schema.org/'
        ),
        'jsonld.type', 'ObservationProperties',
        'dataSource', 'local'
    ) AS "PROPERTIES"
FROM observation o
ORDER BY o.result_time DESC;
