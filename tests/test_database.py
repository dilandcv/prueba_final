"""Pruebas unitarias y de validación estática para el modelo de datos en PostgreSQL."""
from pathlib import Path
import pytest
from sqlfluff.core import Linter, FluffConfig
from src.common.db import get_db_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"


def test_sql_files_exist_and_ordered():
    """Verifica que existan los scripts de inicialización en el orden requerido."""
    expected_files = [
        "01_init_roles.sql",
        "02_init_schemas.sql",
        "03_init_tables.sql",
        "04_grant_permissions.sql",
    ]
    for filename in expected_files:
        file_path = SQL_DIR / filename
        assert file_path.exists(), f"El script SQL '{filename}' debe existir en sql/"


def test_sql_syntax_postgres_dialect():
    """Valida la sintaxis de todos los archivos SQL contra el dialecto PostgreSQL con sqlfluff."""
    config = FluffConfig.from_kwargs(dialect="postgres")
    linter = Linter(config=config)

    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        linted = linter.lint_path(str(sql_file))
        # Verifica que el parseo sea válido (sin errores sintácticos de nivel parsing)
        parse_errors = [
            v for v in linted.get_violations()
            if v.rule_code() == "PRS" or "parsing" in v.description.lower()
        ]
        assert not parse_errors, f"Errores de sintaxis PostgreSQL en {sql_file.name}: {parse_errors}"


def test_schema_definitions():
    """Verifica la creación de todos los esquemas requeridos."""
    schema_sql = (SQL_DIR / "02_init_schemas.sql").read_text(encoding="utf-8").lower()
    expected_schemas = ["bronze", "silver", "gold", "metrics", "ops"]
    for schema in expected_schemas:
        assert f"create schema if not exists {schema}" in schema_sql, f"Falta crear esquema '{schema}'"


def test_table_definitions_and_constraints():
    """Verifica que las tablas medulares, PKs y restricciones CHECK estén definidas."""
    tables_sql = (SQL_DIR / "03_init_tables.sql").read_text(encoding="utf-8").lower()

    # Tablas obligatorias
    expected_tables = [
        "bronze.earthquakes",
        "silver.earthquakes",
        "silver._staging_earthquakes",
        "gold.earthquakes",
        "gold.hourly_regional_stats",
        "gold.magnitude_distribution",
        "gold.regional_ranking",
        "metrics.data_quality",
        "ops.ingestion_watermark",
        "ops.data_availability",
        "ops.ai_executions",
        "ops.anomaly_alerts",
    ]
    for table in expected_tables:
        assert f"create table if not exists {table}" in tables_sql, f"Falta crear la tabla '{table}'"

    # Restricciones esenciales
    assert "chk_silver_magnitude check (magnitude between -2.0 and 10.0)" in tables_sql
    assert "chk_silver_longitude check (longitude between -180.0 and 180.0)" in tables_sql
    assert "chk_silver_latitude check (latitude between -90.0 and 90.0)" in tables_sql
    assert "chk_metrics_score check (quality_score between 0.0 and 100.0)" in tables_sql
    assert "chk_ai_status check (status in ('success', 'fallback', 'error'))" in tables_sql


def test_no_quarantine_tables():
    """Garantiza la regla arquitectónica de NO crear tablas de cuarentena ni de registros inválidos."""
    forbidden_terms = ["quarantine", "cuarentena", "invalid_records", "rejected_events", "bad_records"]

    for sql_file in SQL_DIR.glob("*.sql"):
        content = sql_file.read_text(encoding="utf-8").lower()
        for term in forbidden_terms:
            assert f"table if not exists {term}" not in content, f"Tabla de cuarentena prohibida detectada en {sql_file.name}: {term}"
            assert f"table {term}" not in content, f"Tabla de cuarentena prohibida detectada en {sql_file.name}: {term}"


def test_role_permissions_segregation():
    """Garantiza el modelo de privilegios mínimos para pipeline, api_reader y ai_reader."""
    perm_sql = (SQL_DIR / "04_grant_permissions.sql").read_text(encoding="utf-8").lower()

    # pipeline tiene todos los privilegios
    assert "grant usage, create on schema bronze, silver, gold, metrics, ops to pipeline" in perm_sql
    assert "grant all privileges on all tables in schema bronze, silver, gold, metrics, ops to pipeline" in perm_sql

    # api_reader solo lee gold, metrics.data_quality, ops.anomaly_alerts y data_availability
    assert "revoke all on schema bronze, silver from api_reader" in perm_sql
    assert "grant select on all tables in schema gold to api_reader" in perm_sql
    assert "grant select on metrics.data_quality to api_reader" in perm_sql
    assert "grant select on ops.anomaly_alerts to api_reader" in perm_sql
    assert "grant select on ops.data_availability to api_reader" in perm_sql

    # ai_reader solo lee vistas/tablas agregadas de gold y alertas de anomalías
    assert "revoke all on schema bronze, silver, metrics from ai_reader" in perm_sql
    assert "grant select on gold.hourly_regional_stats to ai_reader" in perm_sql
    assert "grant select on ops.anomaly_alerts to ai_reader" in perm_sql


def test_db_connection_role_resolution(clean_env, monkeypatch):
    """Verifica la resolución correcta de credenciales según el rol sin conectar a un socket activo."""
    # Mockear psycopg.connect para verificar qué parámetros se le envían
    connected_params = {}

    def mock_connect(**kwargs):
        connected_params.update(kwargs)
        class DummyConn:
            def close(self):
                pass
        return DummyConn()

    monkeypatch.setattr("psycopg.connect", mock_connect)

    with get_db_connection("api_reader") as conn:
        assert conn is not None
        assert connected_params["user"] == "api_reader"
        assert connected_params["password"] == "api_reader_example_password"

    with get_db_connection("ai_reader") as conn:
        assert conn is not None
        assert connected_params["user"] == "ai_reader"
        assert connected_params["password"] == "ai_reader_example_password"

    with get_db_connection("pipeline") as conn:
        assert conn is not None
        assert connected_params["user"] == "pipeline"
        assert connected_params["password"] == "pipeline_example_password"
