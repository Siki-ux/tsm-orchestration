-- TSM-TEMP-DISABLED: Local FROST view for THINGS (replaces SMS-based view)
-- This view queries local 'thing' table instead of public.sms_configuration
-- To revert: Delete this file and set USE_LOCAL_STA_VIEWS=false

DROP VIEW IF EXISTS "THINGS" CASCADE;
CREATE VIEW "THINGS" AS
SELECT
    t.id AS "ID",
    t.description AS "DESCRIPTION",
    t.name AS "NAME",
    (CASE 
        WHEN jsonb_typeof(t.properties) = 'object' THEN t.properties
        WHEN jsonb_typeof(t.properties) = 'array' AND jsonb_array_length(t.properties) > 1 THEN t.properties->1
        WHEN t.properties IS NULL THEN '{}'::jsonb
        ELSE jsonb_build_object('wrapped_value', t.properties)
    END) || jsonb_build_object('uuid', t.uuid) AS "PROPERTIES",
    t.uuid AS "UUID"
FROM thing t
ORDER BY t.id ASC;
