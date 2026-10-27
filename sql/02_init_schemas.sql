-- ==============================================================================
-- 02_init_schemas.sql
-- Creación de esquemas de datos y operativos
-- ==============================================================================

-- Esquema Bronze: Datos en bruto de la API del USGS (append-only)
CREATE SCHEMA IF NOT EXISTS bronze;
COMMENT ON SCHEMA bronze IS 'Capa Bronze: Datos originales de la API del USGS en formato JSONB crudo (append-only).';

-- Esquema Silver: Eventos limpios, tipados, deduplicados y validados con Spark
CREATE SCHEMA IF NOT EXISTS silver;
COMMENT ON SCHEMA silver IS 'Capa Silver: Eventos sísmicos normalizados y validados por Spark (1 fila por event_id).';

-- Esquema Gold: Tablas y vistas analíticas agregadas listas para consulta
CREATE SCHEMA IF NOT EXISTS gold;
COMMENT ON SCHEMA gold IS 'Capa Gold: Datos agregados y optimizados para FastAPI, el dashboard y la IA.';

-- Esquema Metrics: Auditoría y contadores de calidad de datos
CREATE SCHEMA IF NOT EXISTS metrics;
COMMENT ON SCHEMA metrics IS 'Métricas operativas de calidad de datos por lote (sin almacenar registros inválidos).';

-- Esquema Ops: Control operativo de ingestas, disponibilidad, anomalías y ejecuciones de IA
CREATE SCHEMA IF NOT EXISTS ops;
COMMENT ON SCHEMA ops IS 'Control operativo, marcas de agua, alertas de anomalías y seguimiento de IA.';
