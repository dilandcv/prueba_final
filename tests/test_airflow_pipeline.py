"""Pruebas unitarias y de integración para la orquestación con Apache Airflow."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest
from dags.dag_usgs_pipeline import dag
from src.pipeline.tasks import (
    determine_query_interval,
    evaluate_data_quality_task,
    extract_usgs_events,
    load_events_to_bronze,
    publish_data_availability_task,
    record_pipeline_execution_task,
    run_spark_bronze_to_silver_task,
    run_spark_silver_to_gold_task,
)


# ==============================================================================
# 1. Pruebas de Integridad, Estructura y Orden del DAG
# ==============================================================================
def test_dag_integrity_and_specifications():
    """Verifica que el DAG cumpla con las restricciones de orquestación requeridas."""
    assert dag is not None
    assert dag.dag_id == "usgs_seismic_pipeline"
    assert dag.schedule_interval == timedelta(minutes=15)
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert getattr(dag, "is_paused_upon_creation", False) is False
    assert dag.doc_md is not None
    assert "USGS" in dag.doc_md


def test_dag_tasks_and_topological_order():
    """Verifica que el DAG contenga exactamente las 8 tareas en el orden secuencial estricto."""
    expected_order = [
        "determine_query_interval",
        "extract_usgs_events",
        "load_events_to_bronze",
        "run_spark_bronze_to_silver",
        "run_spark_silver_to_gold",
        "evaluate_data_quality",
        "record_pipeline_execution",
        "publish_data_availability",
    ]

    task_map = {t.task_id: t for t in dag.tasks}
    assert len(dag.tasks) == 8

    for task_id in expected_order:
        assert task_id in task_map, f"Falta la tarea {task_id} en el DAG."

    for i in range(len(expected_order) - 1):
        curr_task = task_map[expected_order[i]]
        next_task_id = expected_order[i + 1]
        downstream_ids = [t.task_id for t in curr_task.downstream_list]
        assert (
            next_task_id in downstream_ids
        ), f"La tarea {curr_task.task_id} debe anteceder inmediatamente a {next_task_id}"


# ==============================================================================
# 2. Pruebas Unitarias de Tareas Modulares
# ==============================================================================
def test_determine_query_interval_initial_and_incremental(monkeypatch):
    """Verifica el cálculo del intervalo para primera carga y carga incremental."""
    # Simulación 1: Primera carga (sin marca de agua previa)
    mock_service = MagicMock()
    mock_service.get_watermark.return_value = None

    with patch("src.pipeline.tasks.USGSIngestionService", return_value=mock_service):
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        with patch("src.pipeline.tasks.get_db_connection", return_value=mock_conn):
            res_initial = determine_query_interval()
            assert res_initial["is_initial_load"] is True
            assert "starttime" in res_initial
            assert "endtime" in res_initial
            assert "batch_id" in res_initial

    # Simulación 2: Carga incremental (con marca de agua)
    existing_wm = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    mock_service.get_watermark.return_value = existing_wm

    with patch("src.pipeline.tasks.USGSIngestionService", return_value=mock_service):
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        with patch("src.pipeline.tasks.get_db_connection", return_value=mock_conn):
            res_incremental = determine_query_interval()
            assert res_incremental["is_initial_load"] is False
            assert res_incremental["updatedafter"] == existing_wm.isoformat()
            assert "batch_id" in res_incremental


def test_extract_usgs_events_success():
    """Verifica la extracción delegada al cliente de USGS."""
    mock_client = MagicMock()
    mock_features = [{"id": "us100", "properties": {"mag": 4.5}}]
    mock_client.fetch_events.return_value = mock_features

    interval_info = {
        "batch_id": str(uuid.uuid4()),
        "is_initial_load": False,
        "updatedafter": "2026-10-27T12:00:00+00:00",
    }

    with patch("src.pipeline.tasks.USGSClient", return_value=mock_client):
        res = extract_usgs_events(interval_info=interval_info)
        assert res["record_count"] == 1
        assert res["features"] == mock_features
        assert res["batch_id"] == interval_info["batch_id"]


def test_load_events_to_bronze_flow():
    """Verifica la inserción de eventos en Bronze y persistencia de watermark."""
    test_batch_id = str(uuid.uuid4())
    mock_features = [
        {"id": "us101", "properties": {"mag": 3.2, "updated": 1729000000000}},
    ]
    extraction_info = {
        "batch_id": test_batch_id,
        "features": mock_features,
        "record_count": 1,
    }

    mock_service = MagicMock()
    mock_service.insert_bronze_records.return_value = 1

    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn

    with patch("src.pipeline.tasks.USGSIngestionService", return_value=mock_service):
        with patch("src.pipeline.tasks.get_db_connection", return_value=mock_conn):
            res = load_events_to_bronze(extraction_info=extraction_info)
            assert res["batch_id"] == test_batch_id
            assert res["records_ingested"] == 1
            mock_service.insert_bronze_records.assert_called_once()
            mock_service.save_watermark.assert_called_once()


def test_spark_environment_preconditions(monkeypatch):
    """Verifica que run_spark_bronze_to_silver_task valida la existencia del driver JDBC."""
    # Simula ruta JAR inexistente
    monkeypatch.setenv("SPARK_JDBC_JAR", "/ruta/inexistente/driver.jar")
    with pytest.raises(FileNotFoundError, match="El driver JDBC de PostgreSQL no se encuentra"):
        run_spark_bronze_to_silver_task(batch_id=str(uuid.uuid4()))


# ==============================================================================
# 3. Pruebas de Fallos Controlados y Recuperación Idempotente
# ==============================================================================
def test_simulated_api_failure_and_retries():
    """Simula fallo en la API y verifica que extract_usgs_events propaga el error para reintento."""
    mock_client = MagicMock()
    mock_client.fetch_events.side_effect = RuntimeError("Error de conexión a la API USGS")

    interval_info = {
        "batch_id": str(uuid.uuid4()),
        "is_initial_load": True,
        "starttime": "2026-10-20T00:00:00+00:00",
        "endtime": "2026-10-27T00:00:00+00:00",
    }

    with patch("src.pipeline.tasks.USGSClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="Error de conexión a la API USGS"):
            extract_usgs_events(interval_info=interval_info)


def test_quality_check_threshold_failure():
    """Simula un puntaje de calidad bajo e interrupción controlada antes de marcar disponibilidad."""
    mock_cursor = MagicMock()
    # Simula quality_score de 45.0% (por debajo del umbral mínimo de 70.0%)
    mock_cursor.fetchone.side_effect = [
        (45.0, 10, 4, 6, {"rule_magnitude_valid": 6}),
        (10,),  # silver count
        (10,),  # gold count
    ]

    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("src.pipeline.tasks.get_db_connection", return_value=mock_conn):
        with pytest.raises(ValueError, match="Umbral de calidad no superado"):
            evaluate_data_quality_task(batch_id=str(uuid.uuid4()), min_quality_score=70.0)


def test_record_pipeline_execution_and_publish_availability():
    """Verifica que el registro de auditoría y la publicación de disponibilidad operan correctamente."""
    test_batch_id = str(uuid.uuid4())

    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("src.pipeline.tasks.get_db_connection", return_value=mock_conn):
        # 1. Auditoría operativa
        rec_res = record_pipeline_execution_task(
            batch_id=test_batch_id,
            run_id="test_run_123",
        )
        assert rec_res["status"] == "RECORDED"
        assert rec_res["batch_id"] == test_batch_id
        mock_cursor.execute.assert_called_once()

        mock_cursor.reset_mock()

        # 2. Publicación de disponibilidad
        pub_res = publish_data_availability_task(
            batch_id=test_batch_id,
            records_processed=15,
        )
        assert pub_res["status"] == "AVAILABLE"
        assert pub_res["records_processed"] == 15
        mock_cursor.execute.assert_called_once()
