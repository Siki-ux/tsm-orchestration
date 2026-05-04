-- Add properties column to ext_api_type table
-- Mirrors V2_27 which added properties to mqtt_device_type
-- Used to store custom syncer script location (script_bucket, script_path)
ALTER TABLE config_db.ext_api_type
ADD COLUMN IF NOT EXISTS properties jsonb;
