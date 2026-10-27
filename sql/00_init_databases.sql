-- ==============================================================================
-- 00_init_databases.sql
-- Creación idempotente de bases de datos adicionales (ej. OpenMetadata)
-- ==============================================================================

SELECT 'CREATE DATABASE openmetadata_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openmetadata_db')\gexec
