-- ==============================================================================
-- 04_grant_permissions.sql
-- Asignación de permisos según el modelo de privilegios mínimos
-- ==============================================================================

-- Revocación de permisos públicos por defecto en los esquemas
REVOKE ALL ON SCHEMA bronze, silver, gold, metrics, ops FROM PUBLIC;

-- ------------------------------------------------------------------------------
-- 1. Permisos para ROL pipeline (Airflow / Spark)
-- Acceso de lectura y escritura en todas las capas del almacén y tablas operativas
-- ------------------------------------------------------------------------------
GRANT USAGE, CREATE ON SCHEMA bronze, silver, gold, metrics, ops TO pipeline;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bronze, silver, gold, metrics, ops TO pipeline;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bronze, silver, gold, metrics, ops TO pipeline;

ALTER DEFAULT PRIVILEGES IN SCHEMA bronze, silver, gold, metrics, ops
GRANT ALL PRIVILEGES ON TABLES TO pipeline;

ALTER DEFAULT PRIVILEGES IN SCHEMA bronze, silver, gold, metrics, ops
GRANT ALL PRIVILEGES ON SEQUENCES TO pipeline;

-- Asignación de propiedad de las tablas staging al rol pipeline para permitir TRUNCATE / OVERWRITE de Spark
ALTER TABLE silver._staging_earthquakes OWNER TO pipeline;
ALTER TABLE gold._staging_earthquakes OWNER TO pipeline;
ALTER TABLE gold._staging_hourly_regional_stats OWNER TO pipeline;
ALTER TABLE gold._staging_magnitude_distribution OWNER TO pipeline;
ALTER TABLE gold._staging_regional_ranking OWNER TO pipeline;


-- ------------------------------------------------------------------------------
-- 2. Permisos para ROL api_reader (FastAPI Backend)
-- Solo lectura sobre Gold, calidad y alertas operativas. Sin acceso a Bronze ni Silver.
-- ------------------------------------------------------------------------------
REVOKE ALL ON SCHEMA bronze, silver FROM api_reader;

GRANT USAGE ON SCHEMA gold, metrics, ops TO api_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA gold TO api_reader;
GRANT SELECT ON metrics.data_quality TO api_reader;
GRANT SELECT ON ops.anomaly_alerts TO api_reader;
GRANT SELECT ON ops.data_availability TO api_reader;
GRANT SELECT ON ops.pipeline_executions TO api_reader;
GRANT SELECT ON ops.ai_executions TO api_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA gold
GRANT SELECT ON TABLES TO api_reader;


-- ------------------------------------------------------------------------------
-- 3. Permisos para ROL ai_reader (Componente invocador de IA)
-- Solo lectura sobre tablas analíticas agregadas de Gold y alertas de Ops.
-- ------------------------------------------------------------------------------
REVOKE ALL ON SCHEMA bronze, silver, metrics FROM ai_reader;

GRANT USAGE ON SCHEMA gold, ops TO ai_reader;

GRANT SELECT ON gold.earthquakes TO ai_reader;
GRANT SELECT ON gold.hourly_regional_stats TO ai_reader;
GRANT SELECT ON gold.regional_ranking TO ai_reader;
GRANT SELECT ON gold.magnitude_distribution TO ai_reader;
GRANT SELECT ON ops.anomaly_alerts TO ai_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA gold
GRANT SELECT ON TABLES TO ai_reader;
