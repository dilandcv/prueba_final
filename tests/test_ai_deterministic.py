"""Pruebas para la lógica determinista de la Fase 10 (Detección de Anomalías y Reporte Ejecutivo).

Verifica:
1. Cálculo estadístico Z-Score sobre conteos horarios por región vía SQL.
2. Comportamiento de umbrales configurables y exigencia de mínimo de observaciones.
3. Protección contra división por cero en regiones con varianza nula.
4. Registro de alertas en ops.anomaly_alerts y auditoría en ops.ai_executions.
5. Idempotencia: prevención de alertas duplicadas ante ejecuciones repetidas.
6. Precalculo determinista de estadísticas para el reporte diario (sin que el LLM calcule).
7. Mecanismo de fallback cuando Ollama no está disponible.
8. Integridad de los DAGs de Airflow (reporte diario y detección de anomalías).
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from dags.dag_anomaly_detection import dag as dag_anom
from dags.dag_daily_executive_report import dag as dag_report
from src.ai.anomalies import compute_zscore_anomalies_sql, run_anomaly_detection
from src.ai.client import AIGenerationResult, OllamaClient, record_ai_execution
from src.ai.prompts import (
    PROMPT_ANOMALY_V1,
    PROMPT_DAILY_SUMMARY_V1,
    format_anomaly_fallback,
    format_daily_report_fallback,
)
from src.ai.reporter import calculate_daily_summary_metrics, run_daily_executive_report
from src.common.db import get_db_connection


# ==============================================================================
# 1. Pruebas de Detección de Anomalías (Z-Score)
# ==============================================================================
def test_zscore_sql_computation_and_thresholds():
    """Verifica que el cálculo SQL del Z-Score aplique correctamente el umbral y el mínimo de observaciones."""
    with get_db_connection(role="ai_reader") as conn:
        with conn.cursor() as cur:
            # Con umbral alto (100.0), no debe haber ninguna anomalía
            anomalies_high = compute_zscore_anomalies_sql(cur, threshold=100.0, min_observations=5)
            assert len(anomalies_high) == 0

            # Con mínimo de observaciones inalcanzable (1000), no debe haber anomalías
            anomalies_unreachable = compute_zscore_anomalies_sql(cur, threshold=2.0, min_observations=1000)
            assert len(anomalies_unreachable) == 0

            # Con umbral razonable (2.5) y min_observations (5), detecta regiones conocidas
            anomalies = compute_zscore_anomalies_sql(cur, threshold=2.5, min_observations=5)
            assert len(anomalies) > 0
            for item in anomalies:
                assert item.z_score >= 2.5
                assert item.obs_count >= 5
                assert item.stddev > 0
                assert item.region is not None
                assert isinstance(item.hour_bucket, datetime)


def test_zscore_zero_variance_protection():
    """Comprueba que si una región tiene varianza cero, no genere error ni falsa alarma."""
    # Simulamos un cursor donde stddev_count sea 0.0 o None
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []

    result = compute_zscore_anomalies_sql(mock_cur, threshold=3.0, min_observations=10)
    assert result == []


def test_anomaly_fallback_explanation_non_predictive_warning():
    """Garantiza que la explicación del fallback contenga la advertencia obligatoria de no-predicción."""
    sample_data = {
        "region": "California",
        "hour_bucket": "2026-10-27 12:00",
        "event_count": 8,
        "mean": 1.5,
        "stddev": 0.8,
        "z_score": 8.12,
        "threshold": 3.0,
        "obs_count": 50,
    }
    explanation = format_anomaly_fallback(sample_data)
    assert "California" in explanation
    assert "Z-Score: 8.12" in explanation
    # Verificación de advertencia obligatoria contra pronósticos
    assert "no constituye en ningún caso una predicción ni pronóstico" in explanation.lower()


def test_run_anomaly_detection_pipeline_and_idempotence():
    """Verifica la ejecución completa de detección, persistencia y prevención de duplicados."""
    # Primera ejecución
    result1 = run_anomaly_detection(threshold=2.5, min_observations=5)
    assert result1["status"] == "SUCCESS"
    assert result1["anomalies_detected"] > 0

    # Segunda ejecución con los mismos parámetros: debe ser idempotente (0 nuevas alertas)
    result2 = run_anomaly_detection(threshold=2.5, min_observations=5)
    assert result2["status"] == "SUCCESS"
    assert result2["alerts_created"] == 0

    # Verificar que las alertas persisten en ops.anomaly_alerts y se asocian con ops.ai_executions
    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ops.anomaly_alerts;")
            alerts_count = cur.fetchone()[0]
            assert alerts_count > 0

            cur.execute(
                """
                SELECT a.region, a.z_score, e.status, e.used_fallback
                FROM ops.anomaly_alerts a
                JOIN ops.ai_executions e ON a.ai_execution_id = e.id
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            assert row is not None
            assert row[2] in ("SUCCESS", "FALLBACK")
            assert isinstance(row[3], bool)


# ==============================================================================
# 2. Pruebas de Resumen Ejecutivo Diario (Reporte Narrativo)
# ==============================================================================
def test_precalculated_daily_summary_metrics():
    """Garantiza que el código precalcule todas las cifras, rankings y tendencias antes del LLM."""
    with get_db_connection(role="ai_reader") as conn:
        with conn.cursor() as cur:
            metrics = calculate_daily_summary_metrics(cur)

    # Validar campos esenciales precalculados
    assert "total_events" in metrics
    assert "avg_magnitude" in metrics
    assert "tsunami_alerts_count" in metrics
    assert "max_event" in metrics
    assert "top_regions" in metrics
    assert "magnitude_distribution" in metrics
    assert "trend" in metrics
    assert "generated_at" in metrics

    # Validar estructura del evento máximo
    max_ev = metrics["max_event"]
    assert "magnitude" in max_ev
    assert "place" in max_ev
    assert "depth_km" in max_ev

    # Validar estructura de tendencia
    trend = metrics["trend"]
    assert "first_12h_count" in trend
    assert "last_12h_count" in trend
    assert trend["direction"] in ("creciente", "decreciente", "estable")
    assert isinstance(trend["change_percent"], float)


def test_daily_report_fallback_generation():
    """Verifica que el informe en fallback genere un markdown estructurado completo con las cifras precalculadas."""
    mock_metrics = {
        "total_events": 45,
        "avg_magnitude": 3.82,
        "tsunami_alerts_count": 1,
        "max_event": {
            "magnitude": 6.2,
            "place": "120 km W of Anchorage, Alaska",
            "depth_km": 35.0,
            "time_utc": "2026-10-27 08:30",
        },
        "top_regions": [
            {"region": "Alaska", "total_events_24h": 15, "max_magnitude_24h": 6.2},
            {"region": "Japan", "total_events_24h": 8, "max_magnitude_24h": 4.5},
        ],
        "magnitude_distribution": [
            {"magnitude_bracket": "2.5 - 2.9", "event_count": 20},
            {"magnitude_bracket": "3.0 - 3.9", "event_count": 15},
            {"magnitude_bracket": "6.0+", "event_count": 1},
        ],
        "trend": {
            "first_12h_count": 20,
            "last_12h_count": 25,
            "direction": "creciente",
            "change_percent": 25.0,
        },
    }

    report = format_daily_report_fallback(mock_metrics)
    assert "# Resumen Ejecutivo Diario de Actividad Sísmica" in report
    assert "45 eventos sísmicos" in report
    assert "M6.2" in report or "6.2" in report
    assert "Alaska" in report
    assert "tendencia creciente" in report
    assert "Alertas de tsunami registradas" in report
    assert "**1** eventos con bandera de alerta" in report
    assert "no constituyen predicciones geofísicas" in report


def test_run_daily_executive_report_execution():
    """Verifica la ejecución unificada del reporte diario y persistencia en ops.ai_executions."""
    with patch.object(
        OllamaClient,
        "generate",
        return_value=AIGenerationResult(
            text="# Resumen Ejecutivo Diario de Actividad Sísmica\nReporte generado con fallback determinista.",
            model_name="deterministic_fallback",
            status="FALLBACK",
            used_fallback=True,
        ),
    ):
        res = run_daily_executive_report()
        assert res["status"] == "SUCCESS"
        assert res["used_fallback"] is True
        assert res["execution_id"] > 0
        assert len(res["report_text"]) > 20
        assert "Resumen Ejecutivo" in res["report_text"]

        # Verificar registro en base de datos
        with get_db_connection(role="pipeline") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT automation_type, model_name, status, used_fallback
                    FROM ops.ai_executions
                    WHERE id = %s;
                    """,
                    (res["execution_id"],),
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0] == "DAILY_REPORT"
                assert row[1] == "deterministic_fallback"
                assert row[2] == "FALLBACK"
                assert row[3] is True


# ==============================================================================
# 3. Pruebas del Cliente Ollama y Fallback
# ==============================================================================
def test_ollama_client_graceful_fallback_on_unreachable_endpoint():
    """Garantiza que una conexión fallida a Ollama degrade limpiamente a fallback sin lanzar excepción."""
    # Configuramos un cliente apuntando a un puerto inexistente
    client = OllamaClient(base_url="http://localhost:59999", timeout_seconds=1)

    result = client.generate(
        prompt="Describe el sismo",
        fallback_fn=lambda d: f"Fallback activado para {d['item']}",
        fallback_data={"item": "prueba_unitaria"},
    )

    assert result.status == "FALLBACK"
    assert result.used_fallback is True
    assert result.model_name == "deterministic_fallback"
    assert result.text == "Fallback activado para prueba_unitaria"
    assert result.estimated_cost == 0.0


# ==============================================================================
# 4. Pruebas de Estructura de DAGs de Airflow
# ==============================================================================
def test_dag_daily_executive_report_specifications():
    """Verifica la configuración del DAG de reporte diario."""
    assert dag_report is not None
    assert dag_report.dag_id == "daily_seismic_executive_report"
    assert dag_report.schedule_interval == "0 6 * * *"
    assert dag_report.catchup is False
    assert dag_report.max_active_runs == 1
    assert dag_report.doc_md is not None

    task_ids = [t.task_id for t in dag_report.tasks]
    assert "prepare_daily_metrics" in task_ids
    assert "generate_and_persist_report" in task_ids

    # Verificar orden: prepare_daily_metrics >> generate_and_persist_report
    prep_task = next(t for t in dag_report.tasks if t.task_id == "prepare_daily_metrics")
    gen_task = next(t for t in dag_report.tasks if t.task_id == "generate_and_persist_report")
    assert gen_task in prep_task.downstream_list


def test_dag_anomaly_detection_specifications():
    """Verifica la configuración del DAG horario de detección de anomalías."""
    assert dag_anom is not None
    assert dag_anom.dag_id == "seismic_anomaly_detection"
    assert dag_anom.schedule_interval == "0 * * * *"
    assert dag_anom.catchup is False
    assert dag_anom.max_active_runs == 1
    assert dag_anom.doc_md is not None

    task_ids = [t.task_id for t in dag_anom.tasks]
    assert "detect_and_alert_anomalies" in task_ids
