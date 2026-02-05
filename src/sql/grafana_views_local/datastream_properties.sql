-- TSM-TEMP-DISABLED: Local Grafana view for datastream_properties (replaces SMS-based view)
-- This view queries local tables only, without SMS dependencies
-- To revert: Delete this file and set USE_LOCAL_STA_VIEWS=false

DROP VIEW IF EXISTS "datastream_properties" CASCADE;
CREATE VIEW "datastream_properties" AS
SELECT DISTINCT
    tsm_ds.position as "property",
    tsm_ds."position",
    tsm_ds.id as "ds_id",
    tsm_t.uuid as "t_uuid"
FROM datastream tsm_ds
JOIN thing tsm_t ON tsm_ds.thing_id = tsm_t.id;
