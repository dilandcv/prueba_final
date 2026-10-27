-- ==============================================================================
-- 03_init_tables.sql
-- Definición de tablas, claves, índices y restricciones
-- REGLA: No existen tablas ni capas de cuarentena. Registros inválidos se descartan.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. CAPA BRONZE (Append-only)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.earthquakes (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(50) NOT NULL,
    batch_id UUID NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

COMMENT ON TABLE bronze.earthquakes IS 'Eventos sísmicos originales en bruto recibidos de la API USGS.';
COMMENT ON COLUMN bronze.earthquakes.payload IS 'Feature completo en GeoJSON original sin transformaciones.';

CREATE INDEX IF NOT EXISTS idx_bronze_event_id ON bronze.earthquakes (event_id);
CREATE INDEX IF NOT EXISTS idx_bronze_ingested_at ON bronze.earthquakes (ingested_at);
CREATE INDEX IF NOT EXISTS idx_bronze_source_updated_at ON bronze.earthquakes (source_updated_at);
CREATE INDEX IF NOT EXISTS idx_bronze_batch_id ON bronze.earthquakes (batch_id);


-- ------------------------------------------------------------------------------
-- 2. CAPA SILVER (Normalizada, tipada y validada por Spark)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.earthquakes (
    event_id VARCHAR(50) PRIMARY KEY,
    magnitude NUMERIC(4,2) NOT NULL,
    place TEXT,
    region VARCHAR(100),
    time_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    depth_km NUMERIC(6,2),
    tsunami_alert BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_silver_magnitude CHECK (magnitude BETWEEN -2.0 AND 10.0),
    CONSTRAINT chk_silver_longitude CHECK (longitude BETWEEN -180.0 AND 180.0),
    CONSTRAINT chk_silver_latitude CHECK (latitude BETWEEN -90.0 AND 90.0)
);

COMMENT ON TABLE silver.earthquakes IS 'Eventos sísmicos normalizados y deduplicados (versión más reciente por event_id).';

CREATE INDEX IF NOT EXISTS idx_silver_time_utc ON silver.earthquakes (time_utc);
CREATE INDEX IF NOT EXISTS idx_silver_magnitude ON silver.earthquakes (magnitude);
CREATE INDEX IF NOT EXISTS idx_silver_region ON silver.earthquakes (region);
CREATE INDEX IF NOT EXISTS idx_silver_coordinates ON silver.earthquakes (latitude, longitude);

-- Tabla de staging técnico para permitir escritura idempotente de Spark por JDBC
CREATE TABLE IF NOT EXISTS silver._staging_earthquakes (
    LIKE silver.earthquakes INCLUDING ALL EXCLUDING CONSTRAINTS
);
COMMENT ON TABLE silver._staging_earthquakes IS 'Tabla intermedia volátil para el patrón Spark JDBC overwrite + SQL Upsert.';


-- ------------------------------------------------------------------------------
-- 3. CAPA GOLD (Agregaciones y vistas analíticas)
-- ------------------------------------------------------------------------------

-- Tabla desnormalizada optimizada para el mapa y filtros rápidos de la API
CREATE TABLE IF NOT EXISTS gold.earthquakes (
    event_id VARCHAR(50) PRIMARY KEY,
    magnitude NUMERIC(4,2) NOT NULL,
    place TEXT,
    region VARCHAR(100),
    time_utc TIMESTAMPTZ NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    depth_km NUMERIC(6,2),
    tsunami_alert BOOLEAN NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE gold.earthquakes IS 'Eventos depurados listos para consumo del mapa y endpoints analíticos.';

CREATE INDEX IF NOT EXISTS idx_gold_time_utc ON gold.earthquakes (time_utc);
CREATE INDEX IF NOT EXISTS idx_gold_magnitude ON gold.earthquakes (magnitude);
CREATE INDEX IF NOT EXISTS idx_gold_region ON gold.earthquakes (region);
CREATE INDEX IF NOT EXISTS idx_gold_tsunami ON gold.earthquakes (tsunami_alert);

-- Estadísticas horarias por región (base para el cálculo del Z-Score de anomalías)
CREATE TABLE IF NOT EXISTS gold.hourly_regional_stats (
    region VARCHAR(100) NOT NULL,
    hour_bucket TIMESTAMPTZ NOT NULL,
    event_count INT NOT NULL DEFAULT 0,
    avg_magnitude NUMERIC(4,2),
    max_magnitude NUMERIC(4,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (region, hour_bucket)
);

COMMENT ON TABLE gold.hourly_regional_stats IS 'Agregados horarios de eventos y magnitudes por región calculados con Spark.';
CREATE INDEX IF NOT EXISTS idx_gold_hourly_bucket ON gold.hourly_regional_stats (hour_bucket);

-- Distribución por rangos de magnitud para gráficos
CREATE TABLE IF NOT EXISTS gold.magnitude_distribution (
    magnitude_bracket VARCHAR(20) PRIMARY KEY,
    event_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE gold.magnitude_distribution IS 'Distribución agregada de sismos por rangos de magnitud.';

-- Ranking de regiones con mayor actividad en las últimas 24 horas
CREATE TABLE IF NOT EXISTS gold.regional_ranking (
    region VARCHAR(100) PRIMARY KEY,
    total_events_24h INT NOT NULL DEFAULT 0,
    max_magnitude_24h NUMERIC(4,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE gold.regional_ranking IS 'Ranking de regiones más activas en las últimas 24 horas.';

-- Tablas de staging técnico para permitir escritura idempotente de Spark por JDBC en Gold
CREATE TABLE IF NOT EXISTS gold._staging_earthquakes (
    LIKE gold.earthquakes INCLUDING ALL EXCLUDING CONSTRAINTS
);
CREATE TABLE IF NOT EXISTS gold._staging_hourly_regional_stats (
    LIKE gold.hourly_regional_stats INCLUDING ALL EXCLUDING CONSTRAINTS
);
CREATE TABLE IF NOT EXISTS gold._staging_magnitude_distribution (
    LIKE gold.magnitude_distribution INCLUDING ALL EXCLUDING CONSTRAINTS
);
CREATE TABLE IF NOT EXISTS gold._staging_regional_ranking (
    LIKE gold.regional_ranking INCLUDING ALL EXCLUDING CONSTRAINTS
);
COMMENT ON TABLE gold._staging_earthquakes IS 'Tabla intermedia volátil para el patrón Spark JDBC overwrite + SQL Upsert en Gold.';


-- ------------------------------------------------------------------------------
-- 4. ESQUEMA METRICS (Auditoría de calidad)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metrics.data_quality (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_records INT NOT NULL,
    valid_records INT NOT NULL,
    invalid_records INT NOT NULL,
    quality_score NUMERIC(5,2) NOT NULL,
    failed_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_metrics_score CHECK (quality_score BETWEEN 0.0 AND 100.0)
);

COMMENT ON TABLE metrics.data_quality IS 'Puntajes de calidad por lote y desglose agregado de reglas incumplidas.';
CREATE INDEX IF NOT EXISTS idx_metrics_evaluated_at ON metrics.data_quality (evaluated_at);
CREATE INDEX IF NOT EXISTS idx_metrics_batch_id ON metrics.data_quality (batch_id);


-- ------------------------------------------------------------------------------
-- 5. ESQUEMA OPS (Operaciones, Marcas de Agua, Disponibilidad, IA)
-- ------------------------------------------------------------------------------

-- Marca de agua de ingesta incremental para USGS updatedafter
CREATE TABLE IF NOT EXISTS ops.ingestion_watermark (
    source_name VARCHAR(50) PRIMARY KEY,
    last_success_timestamp TIMESTAMPTZ NOT NULL,
    last_batch_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ops.ingestion_watermark IS 'Última marca temporal procesada con éxito para la ingesta incremental.';

-- Registro de disponibilidad de datos para sincronización con FastAPI y SSE
CREATE TABLE IF NOT EXISTS ops.data_availability (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    records_processed INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'
);

COMMENT ON TABLE ops.data_availability IS 'Registro de lotes completados para notificación al backend y frontend vía SSE.';
CREATE INDEX IF NOT EXISTS idx_ops_available_at ON ops.data_availability (available_at);

-- Registro consolidado de ejecuciones de pipelines (Airflow)
CREATE TABLE IF NOT EXISTS ops.pipeline_executions (
    id BIGSERIAL PRIMARY KEY,
    dag_id VARCHAR(100) NOT NULL,
    run_id VARCHAR(100) NOT NULL,
    batch_id UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_seconds NUMERIC(8,2) NOT NULL DEFAULT 0.0,
    records_ingested INT NOT NULL DEFAULT 0,
    quality_score NUMERIC(5,2),
    status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE ops.pipeline_executions IS 'Registro consolidado de ejecuciones de pipelines para observabilidad y auditoría.';
CREATE INDEX IF NOT EXISTS idx_ops_pipeline_batch_id ON ops.pipeline_executions (batch_id);
CREATE INDEX IF NOT EXISTS idx_ops_pipeline_run_id ON ops.pipeline_executions (run_id);

-- Seguimiento de ejecuciones del módulo de IA
CREATE TABLE IF NOT EXISTS ops.ai_executions (
    id BIGSERIAL PRIMARY KEY,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    automation_type VARCHAR(50) NOT NULL,
    prompt_version VARCHAR(20) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    input_tokens INT,
    output_tokens INT,
    latency_ms INT,
    estimated_cost NUMERIC(8,6) NOT NULL DEFAULT 0.0,
    used_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    airflow_run_id VARCHAR(100),
    CONSTRAINT chk_ai_status CHECK (status IN ('SUCCESS', 'FALLBACK', 'ERROR'))
);

COMMENT ON TABLE ops.ai_executions IS 'Auditoría detallada de llamadas al modelo de IA local (tokens, latencia, fallback).';
CREATE INDEX IF NOT EXISTS idx_ops_ai_executed_at ON ops.ai_executions (executed_at);

-- Alertas de anomalías detectadas (Z-score sobre conteos horarios por región)
CREATE TABLE IF NOT EXISTS ops.anomaly_alerts (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    region VARCHAR(100) NOT NULL,
    hour_bucket TIMESTAMPTZ NOT NULL,
    event_count INT NOT NULL,
    z_score NUMERIC(5,2) NOT NULL,
    threshold NUMERIC(5,2) NOT NULL,
    narrative_explanation TEXT NOT NULL,
    ai_execution_id BIGINT REFERENCES ops.ai_executions(id) ON DELETE SET NULL
);

COMMENT ON TABLE ops.anomaly_alerts IS 'Alertas de actividad sísmica inusual basadas en Z-Score estadístico y explicadas por IA.';
CREATE INDEX IF NOT EXISTS idx_ops_anomaly_detected_at ON ops.anomaly_alerts (detected_at);
CREATE INDEX IF NOT EXISTS idx_ops_anomaly_region ON ops.anomaly_alerts (region);

-- Documentación técnica indexada para recuperación RAG
CREATE TABLE IF NOT EXISTS ops.project_documents (
    id SERIAL PRIMARY KEY,
    doc_name VARCHAR(100) NOT NULL,
    section_title VARCHAR(200) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', doc_name || ' ' || section_title || ' ' || content)) STORED
);

COMMENT ON TABLE ops.project_documents IS 'Documentación técnica del proyecto fragmentada para búsqueda RAG con FTS.';
CREATE INDEX IF NOT EXISTS idx_ops_doc_tsv ON ops.project_documents USING GIN (tsv);

-- Trazabilidad detallada del agente conversacional
CREATE TABLE IF NOT EXISTS ops.ai_agent_traces (
    id BIGSERIAL PRIMARY KEY,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    question TEXT NOT NULL,
    intent VARCHAR(50) NOT NULL,
    tools_used JSONB NOT NULL DEFAULT '[]'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    latency_ms INT NOT NULL DEFAULT 0,
    used_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    rejection_reason TEXT
);

COMMENT ON TABLE ops.ai_agent_traces IS 'Trazabilidad y observabilidad de consultas, intenciones y herramientas ejecutadas por el agente.';
CREATE INDEX IF NOT EXISTS idx_ops_traces_executed_at ON ops.ai_agent_traces (executed_at);
CREATE INDEX IF NOT EXISTS idx_ops_traces_intent ON ops.ai_agent_traces (intent);

