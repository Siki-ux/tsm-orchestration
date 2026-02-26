-- Allow multiple s3_stores to share the same file_parser.
-- The original UNIQUE constraint on file_parser_id prevented parser reuse
-- across sensors, which is needed for SFTP ingestion where multiple sensors
-- may reference the same CSV parser.
ALTER TABLE config_db.s3_store DROP CONSTRAINT IF EXISTS s3_store_file_parser_id_key;
