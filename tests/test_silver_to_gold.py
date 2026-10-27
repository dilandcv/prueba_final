"""Pruebas unitarias para las transformaciones analíticas Silver a Gold con PySpark."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from src.processing.silver_to_gold import (
    build_gold_earthquakes,
    build_hourly_regional_stats,
    build_magnitude_distribution,
    build_regional_ranking_24h,
    execute_gold_upsert,
)
from src.processing.spark_session import build_spark_session


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """SparkSession local para pruebas deterministas de Gold."""
    session = build_spark_session("SilverToGoldTests", master="local[1]")
    yield session
    session.stop()


@pytest.fixture
def mock_silver_df(spark) -> SparkSession:
    """DataFrame determinista que simula eventos limpios en Silver."""
    return spark.sql("""
        SELECT
            'evt_1' AS event_id,
            CAST(3.5 AS DOUBLE) AS magnitude,
            '10 km NE of Ridgecrest, CA' AS place,
            'CA' AS region,
            TIMESTAMP '2026-10-25 14:15:00' AS time_utc,
            CAST(-117.5 AS DOUBLE) AS longitude,
            CAST(35.5 AS DOUBLE) AS latitude,
            CAST(6.2 AS DOUBLE) AS depth_km,
            FALSE AS tsunami_alert,
            TIMESTAMP '2026-10-25 14:20:00' AS updated_at_utc
        UNION ALL
        SELECT
            'evt_2' AS event_id,
            CAST(4.5 AS DOUBLE) AS magnitude,
            '15 km NE of Ridgecrest, CA' AS place,
            'CA' AS region,
            TIMESTAMP '2026-10-25 14:45:00' AS time_utc,
            CAST(-117.4 AS DOUBLE) AS longitude,
            CAST(35.6 AS DOUBLE) AS latitude,
            CAST(5.8 AS DOUBLE) AS depth_km,
            FALSE AS tsunami_alert,
            TIMESTAMP '2026-10-25 14:50:00' AS updated_at_utc
        UNION ALL
        SELECT
            'evt_3' AS event_id,
            CAST(5.2 AS DOUBLE) AS magnitude,
            '20 km S of Whites City, New Mexico' AS place,
            'New Mexico' AS region,
            TIMESTAMP '2026-10-25 14:10:00' AS time_utc,
            CAST(-104.3 AS DOUBLE) AS longitude,
            CAST(32.1 AS DOUBLE) AS latitude,
            CAST(10.0 AS DOUBLE) AS depth_km,
            FALSE AS tsunami_alert,
            TIMESTAMP '2026-10-25 14:15:00' AS updated_at_utc
        UNION ALL
        SELECT
            'evt_4' AS event_id,
            CAST(2.8 AS DOUBLE) AS magnitude,
            '5 km W of Ridgecrest, CA' AS place,
            'CA' AS region,
            TIMESTAMP '2026-10-25 15:05:00' AS time_utc, -- Siguiente hora
            CAST(-117.6 AS DOUBLE) AS longitude,
            CAST(35.4 AS DOUBLE) AS latitude,
            CAST(4.1 AS DOUBLE) AS depth_km,
            FALSE AS tsunami_alert,
            TIMESTAMP '2026-10-25 15:10:00' AS updated_at_utc
    """)


def test_build_gold_earthquakes_schema_and_integrity(mock_silver_df):
    """Verifica que gold.earthquakes conserve todos los campos limpios necesarios para el mapa."""
    gold_df = build_gold_earthquakes(mock_silver_df)
    assert gold_df.count() == 4

    expected_cols = {
        "event_id", "magnitude", "place", "region", "time_utc",
        "longitude", "latitude", "depth_km", "tsunami_alert", "updated_at_utc"
    }
    assert set(gold_df.columns) == expected_cols


def test_build_hourly_regional_stats(mock_silver_df):
    """Verifica las agregaciones horarias por región y conteos para detección de anomalías."""
    stats_df = build_hourly_regional_stats(mock_silver_df)
    rows = stats_df.collect()

    assert len(rows) == 3  # (CA, lote 1), (New Mexico, lote 1), (CA, lote 2)

    # Fila de CA con 2 eventos (evt_1 y evt_2 en la misma hora)
    ca_lote1 = [r for r in rows if r["region"] == "CA" and r["event_count"] == 2][0]
    assert ca_lote1["event_count"] == 2
    assert float(ca_lote1["avg_magnitude"]) == 4.0   # (3.5 + 4.5) / 2
    assert float(ca_lote1["max_magnitude"]) == 4.5

    # New Mexico (evt_3)
    nm = [r for r in rows if r["region"] == "New Mexico"][0]
    assert nm["event_count"] == 1
    assert float(nm["max_magnitude"]) == 5.2

    # CA en la siguiente hora (evt_4)
    ca_lote2 = [r for r in rows if r["region"] == "CA" and r["event_count"] == 1][0]
    assert ca_lote2["event_count"] == 1
    assert float(ca_lote2["max_magnitude"]) == 2.8
    assert ca_lote2["hour_bucket"] > ca_lote1["hour_bucket"]


def test_build_magnitude_distribution(mock_silver_df):
    """Verifica la clasificación agregada en rangos de magnitud."""
    dist_df = build_magnitude_distribution(mock_silver_df)
    results = {r["magnitude_bracket"]: r["event_count"] for r in dist_df.collect()}

    # evt_4: 2.8 -> "2.5 - 2.9"
    # evt_1: 3.5 -> "3.0 - 3.9"
    # evt_2: 4.5 -> "4.0 - 4.9"
    # evt_3: 5.2 -> "5.0 - 5.9"
    assert results.get("2.5 - 2.9") == 1
    assert results.get("3.0 - 3.9") == 1
    assert results.get("4.0 - 4.9") == 1
    assert results.get("5.0 - 5.9") == 1


def test_build_regional_ranking_24h(mock_silver_df):
    """Verifica el ranking de regiones activas ordenado descendentemente por cantidad y magnitud."""
    ref_time = datetime(2026, 10, 25, 20, 0, 0, tzinfo=timezone.utc)
    ranking_df = build_regional_ranking_24h(mock_silver_df, reference_time=ref_time)
    rows = ranking_df.collect()

    assert len(rows) == 2
    # CA tiene 3 sismos en la ventana, New Mexico tiene 1 sismo
    assert rows[0]["region"] == "CA"
    assert rows[0]["total_events_24h"] == 3
    assert float(rows[0]["max_magnitude_24h"]) == 4.5

    assert rows[1]["region"] == "New Mexico"
    assert rows[1]["total_events_24h"] == 1
    assert float(rows[1]["max_magnitude_24h"]) == 5.2


def test_execute_gold_upsert_idempotence():
    """Verifica la generación y ejecución atómica de sentencias SQL de upsert para Gold."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.rowcount = 4

    results = execute_gold_upsert(mock_conn)

    assert results["earthquakes_upserted"] == 4
    assert results["hourly_stats_upserted"] == 4
    assert results["magnitude_distribution_upserted"] == 4
    assert results["regional_ranking_refreshed"] == 4

    # 4 sentencias principales + 1 truncate para ranking
    assert mock_cursor.execute.call_count == 5

    # Comprueba la presencia de ON CONFLICT DO UPDATE en las sentencias de upsert
    executed_queries = [call[0][0] for call in mock_cursor.execute.call_args_list]
    assert any("ON CONFLICT (event_id) DO UPDATE" in q for q in executed_queries)
    assert any("ON CONFLICT (region, hour_bucket) DO UPDATE" in q for q in executed_queries)
    assert any("ON CONFLICT (magnitude_bracket) DO UPDATE" in q for q in executed_queries)
    assert any("TRUNCATE TABLE gold.regional_ranking" in q for q in executed_queries)
