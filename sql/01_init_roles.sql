-- ==============================================================================
-- 01_init_roles.sql
-- Creación de roles de seguridad con privilegios mínimos
-- ==============================================================================

DO $$
BEGIN
    -- Rol para el pipeline de ingesta y orquestación (Airflow / Spark)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'pipeline') THEN
        CREATE ROLE pipeline WITH LOGIN PASSWORD 'pipeline_example_password';
        COMMENT ON ROLE pipeline IS 'Rol con permisos de lectura y escritura en esquemas de datos y operativos.';
    END IF;

    -- Rol para el backend FastAPI (lectura sobre Gold y tablas públicas autorizadas)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'api_reader') THEN
        CREATE ROLE api_reader WITH LOGIN PASSWORD 'api_reader_example_password';
        COMMENT ON ROLE api_reader IS 'Rol de solo lectura sobre la capa Gold y tablas informativas de auditoría.';
    END IF;

    -- Rol para el módulo de IA local (solo lectura sobre métricas agregadas de Gold)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ai_reader') THEN
        CREATE ROLE ai_reader WITH LOGIN PASSWORD 'ai_reader_example_password';
        COMMENT ON ROLE ai_reader IS 'Rol de solo lectura sobre vistas y tablas analíticas para generación de narrativas.';
    END IF;
END
$$;
