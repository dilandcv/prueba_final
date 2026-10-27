"""Pruebas para el procesamiento de Bronze a Silver con PySpark."""
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from src.processing.bronze_to_silver import (
    deduplicate_events,
    execute_silver_upsert,
    parse_and_normalize_bronze,
    persist_quality_metrics,
)
from src.processing.spark_session import build_spark_session
from src.quality.rules import QualitySummary, evaluate_quality


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """Fixture de SparkSession compartida en modo local[1] para pruebas deterministas."""
    session = build_spark_session("BronzeToSilverUnitTests", master="local[1]")
    yield session
    session.stop()


def test_parse_and_normalize_valid_geojson(spark):
    """Verifica que el parsing de GeoJSON extraiga y normalice todos los campos a Silver."""
    payload_dict = {
        "id": "us7000test",
        "properties": {
            "mag": 4.25,
            "place": "15 km SSW of Volcano, Hawaii",
            "time": 1729000000000,
            "updated": 1729005000000,
            "tsunami": 1,
            "code": "7000test",
        },
        "geometry": {
            "type": "Point",
            "coordinates": [-155.23, 19.42, 8.5],
        },
    }
    escaped_json = json.dumps(payload_dict).replace("'", "''")

    bronze_df = spark.sql(f"""
        SELECT
            'us7000test' AS event_id,
            CURRENT_TIMESTAMP() AS ingested_at,
            TIMESTAMP '2026-10-20 10:00:00' AS source_updated_at,
            '{escaped_json}' AS payload_text
    """)

    normalized = parse_and_normalize_bronze(bronze_df)
    row = normalized.first()

    assert row is not None
    assert row["event_id"] == "us7000test"
    assert row["magnitude"] == 4.25
    assert row["place"] == "15 km SSW of Volcano, Hawaii"
    assert row["region"] == "Hawaii"
    assert row["longitude"] == -155.23
    assert row["latitude"] == 19.42
    assert row["depth_km"] == 8.5
    assert row["tsunami_alert"] is True
    assert isinstance(row["time_utc"], datetime)
    assert isinstance(row["updated_at_utc"], datetime)


def test_region_extraction_rules(spark):
    """Verifica las reglas deterministas de extracción de región a partir de 'place'."""
    sample_df = spark.sql("""
        SELECT '35 km SSE of Whites City, New Mexico' AS place
        UNION ALL SELECT '14 km NE of Ridgecrest, CA' AS place
        UNION ALL SELECT 'off the coast of Oregon' AS place
        UNION ALL SELECT 'Central Alaska' AS place
        UNION ALL SELECT CAST(NULL AS STRING) AS place
    """)

    from src.processing.bronze_to_silver import extract_region_column
    result_df = sample_df.withColumn("region", extract_region_column())
    regions = [r["region"] for r in result_df.collect()]

    assert regions == ["New Mexico", "CA", "Oregon", "Central Alaska", "Unknown"]


def test_quality_evaluation_and_descarte(spark):
    """Verifica la separación en memoria de registros válidos e inválidos y métricas por regla."""
    test_df = spark.sql("""
        SELECT
            'valid_1' AS event_id,
            3.5 AS magnitude,
            TIMESTAMP '2026-10-20 10:00:00' AS time_utc,
            -120.5 AS longitude,
            35.2 AS latitude,
            FALSE AS tsunami_alert
        UNION ALL
        SELECT
            'invalid_mag' AS event_id,
            12.5 AS magnitude, -- Inválida (> 10.0)
            TIMESTAMP '2026-10-20 10:00:00' AS time_utc,
            -120.5 AS longitude,
            35.2 AS latitude,
            FALSE AS tsunami_alert
        UNION ALL
        SELECT
            'invalid_lat' AS event_id,
            4.0 AS magnitude,
            TIMESTAMP '2026-10-20 10:00:00' AS time_utc,
            -120.5 AS longitude,
            95.0 AS latitude, -- Inválida (> 90.0)
            FALSE AS tsunami_alert
        UNION ALL
        SELECT
            NULL AS event_id, -- Inválida (id nulo)
            4.0 AS magnitude,
            TIMESTAMP '2026-10-20 10:00:00' AS time_utc,
            -120.5 AS longitude,
            35.0 AS latitude,
            FALSE AS tsunami_alert
        UNION ALL
        SELECT
            'future_time' AS event_id,
            4.0 AS magnitude,
            TIMESTAMP '2099-01-01 00:00:00' AS time_utc, -- Inválida (fecha futura)
            -120.5 AS longitude,
            35.0 AS latitude,
            FALSE AS tsunami_alert
    """)

    valid_df, invalid_df, summary = evaluate_quality(test_df)

    assert summary.total_records == 5
    assert summary.valid_records == 1
    assert summary.invalid_records == 4
    assert summary.quality_score == 20.0

    # Verificación de contadores de reglas infringidas
    assert summary.failed_rules["rule_magnitude_valid"] == 1
    assert summary.failed_rules["rule_coordinates_valid"] == 1
    assert summary.failed_rules["rule_id_not_null"] == 1
    assert summary.failed_rules["rule_time_valid"] == 1

    # Demostración estricta: los inválidos NO están en valid_df (el que va a Silver)
    valid_ids = [r["event_id"] for r in valid_df.collect()]
    assert valid_ids == ["valid_1"]

    # Los inválidos quedan aislados en memoria
    invalid_ids = [r["event_id"] for r in invalid_df.collect()]
    assert "invalid_mag" in invalid_ids
    assert "invalid_lat" in invalid_ids
    assert "future_time" in invalid_ids


def test_deduplication_preserves_most_recent_version(spark):
    """Verifica que al existir registros duplicados del mismo event_id, se conserve el más reciente."""
    duplicated_df = spark.sql("""
        SELECT
            'evt_duplicate' AS event_id,
            3.0 AS magnitude,
            TIMESTAMP '2026-10-20 08:00:00' AS updated_at_utc,
            TIMESTAMP '2026-10-20 08:00:00' AS source_updated_at
        UNION ALL
        SELECT
            'evt_duplicate' AS event_id,
            3.4 AS magnitude, -- Versión actualizada posterior
            TIMESTAMP '2026-10-20 09:30:00' AS updated_at_utc,
            TIMESTAMP '2026-10-20 09:30:00' AS source_updated_at
    """)

    deduped = deduplicate_events(duplicated_df)
    assert deduped.count() == 1

    row = deduped.first()
    assert float(row["magnitude"]) == 3.4
    assert row["updated_at_utc"].minute == 30


def test_silver_upsert_and_metrics_persistence():
    """Verifica la ejecución de sentencias SQL de upsert y persistencia de métricas de calidad."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.rowcount = 5

    # 1. Prueba de Upsert SQL
    upserted = execute_silver_upsert(mock_conn)
    assert upserted == 5
    mock_cursor.execute.assert_called_once()
    sql_executed = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO silver.earthquakes" in sql_executed
    assert "ON CONFLICT (event_id) DO UPDATE" in sql_executed
    assert "WHERE EXCLUDED.updated_at_utc >= silver.earthquakes.updated_at_utc" in sql_executed

    # 2. Prueba de persistencia de métricas
    test_batch_id = "11111111-2222-3333-4444-555555555555"
    summary = QualitySummary(
        total_records=100,
        valid_records=95,
        invalid_records=5,
        quality_score=95.0,
        failed_rules={"rule_magnitude_valid": 3, "rule_coordinates_valid": 2},
    )
    persist_quality_metrics(mock_conn, test_batch_id, summary)
    assert mock_cursor.execute.call_count == 2
    metrics_sql, params = mock_cursor.execute.call_args_list[1][0]
    assert "INSERT INTO metrics.data_quality" in metrics_sql
    assert params[0] == test_batch_id
    assert params[1] == 100
    assert params[2] == 95
    assert params[3] == 5
    assert params[4] == 95.0
    assert json.loads(params[5]) == {"rule_magnitude_valid": 3, "rule_coordinates_valid": 2}
