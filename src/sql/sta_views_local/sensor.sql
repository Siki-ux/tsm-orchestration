-- Dummy SENSORS view for local FROST setup
DROP VIEW IF EXISTS "SENSORS" CASCADE;
CREATE VIEW "SENSORS" AS
SELECT
    NULL::bigint AS "ID",
    NULL::varchar AS "NAME",
    NULL::varchar AS "DESCRIPTION",
    NULL::varchar AS "ENCODING_TYPE",
    NULL::varchar AS "METADATA"
WHERE false;
