"""Pruebas unitarias y de integración para la API FastAPI y endpoints analíticos."""
import json
import threading
import time
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest

from src.api.main import app
from src.api.services import AnalyticsService
from src.common.config import get_settings


@pytest.fixture
def client():
    """Cliente de pruebas para FastAPI."""
    return TestClient(app)


# ==============================================================================
# 1. Pruebas de Endpoints Analíticos y Filtros (con PostgreSQL vivo o mock)
# ==============================================================================
def test_healthcheck_endpoint(client):
    """Verifica que el endpoint /api/v1/health responda HTTP 200 y reporte conexión a BD."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("UP", "DEGRADED")
    assert "database" in data
    assert "timestamp" in data


def test_general_indicators_endpoint(client):
    """Verifica que el endpoint de indicadores consolidados retorne valores válidos."""
    response = client.get("/api/v1/metrics/indicators")
    assert response.status_code == 200
    data = response.json()
    assert "events_count" in data
    assert "tsunami_alerts_count" in data
    assert "quality_score" in data
    assert isinstance(data["events_count"], int)
    assert 0.0 <= data["quality_score"] <= 100.0


def test_general_indicators_with_filters(client):
    """Verifica la aplicación de filtros por magnitud y región en los indicadores."""
    response = client.get("/api/v1/metrics/indicators?min_magnitude=5.0&region=Indonesia")
    assert response.status_code == 200
    data = response.json()
    assert "events_count" in data
    if data["events_count"] > 0:
        assert data["max_magnitude"] >= 5.0


def test_events_timeseries_endpoint(client):
    """Verifica que el endpoint de serie temporal devuelva la agrupación horaria."""
    response = client.get("/api/v1/events/timeseries")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        point = data[0]
        assert "hour_bucket" in point
        assert "total_events" in point


def test_magnitude_distribution_endpoint(client):
    """Verifica la distribución de sismos por rangos de magnitud."""
    response = client.get("/api/v1/metrics/magnitude-distribution")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "magnitude_bracket" in item
        assert "event_count" in item


def test_regional_ranking_endpoint(client):
    """Verifica el ranking regional de actividad en 24h."""
    response = client.get("/api/v1/metrics/regional-ranking?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5
    if data:
        first = data[0]
        assert "region" in first
        assert "total_events_24h" in first
        assert "rank_position" in first
        assert first["rank_position"] == 1


def test_map_events_endpoint(client):
    """Verifica el endpoint de eventos para mapa geográfico."""
    response = client.get("/api/v1/events/map?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10
    if data:
        ev = data[0]
        assert "event_id" in ev
        assert "latitude" in ev
        assert "longitude" in ev
        assert "magnitude" in ev
        assert "place" in ev
        assert -90.0 <= ev["latitude"] <= 90.0
        assert -180.0 <= ev["longitude"] <= 180.0


def test_quality_summary_endpoint(client):
    """Verifica el resumen de calidad de datos."""
    response = client.get("/api/v1/quality/summary")
    assert response.status_code == 200
    data = response.json()
    assert "quality_score" in data
    assert "valid_records" in data
    assert "invalid_records" in data


def test_alerts_and_pipeline_status_endpoints(client):
    """Verifica los endpoints de alertas y estado del pipeline."""
    # Alertas
    res_alerts = client.get("/api/v1/alerts/anomalies")
    assert res_alerts.status_code == 200
    assert isinstance(res_alerts.json(), list)

    # Reportes IA
    res_reports = client.get("/api/v1/ai/reports")
    assert res_reports.status_code == 200
    assert isinstance(res_reports.json(), list)

    # Estado del pipeline
    res_pipe = client.get("/api/v1/pipeline/status")
    assert res_pipe.status_code == 200
    data_pipe = res_pipe.json()
    assert "status" in data_pipe
    assert "records_processed" in data_pipe


# ==============================================================================
# 2. Pruebas de Validación de Parámetros y Ausencia de Datos
# ==============================================================================
def test_invalid_parameters_validation(client):
    """Verifica que parámetros inválidos generen errores 422 controlados."""
    # Magnitud imposible (> 10.0)
    res1 = client.get("/api/v1/metrics/indicators?min_magnitude=15.0")
    assert res1.status_code == 422

    # Límite fuera de rango permitido (> 2000)
    res2 = client.get("/api/v1/events/map?limit=5000")
    assert res2.status_code == 422


def test_empty_results_handling(client):
    """Verifica que filtros sin coincidencias retornen estructuras vacías limpias."""
    res = client.get("/api/v1/events/map?region=RegionInexistente999")
    assert res.status_code == 200
    assert res.json() == []

    res_ind = client.get("/api/v1/metrics/indicators?region=RegionInexistente999")
    assert res_ind.status_code == 200
    data = res_ind.json()
    assert data["events_count"] == 0
    assert data["max_magnitude"] is None


# ==============================================================================
# 3. Pruebas de Seguridad y Privilegios
# ==============================================================================
def test_api_reader_cannot_modify_or_access_bronze():
    """Verifica el principio de privilegios mínimos: api_reader no accede a capas inferiores."""
    from src.common.db import get_db_connection

    with get_db_connection(role="api_reader") as conn:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("SELECT count(*) FROM bronze.earthquakes;")
            conn.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM gold.earthquakes;")
            conn.rollback()


# ==============================================================================
# 4. Pruebas del Flujo SSE (Server-Sent Events)
# ==============================================================================
def test_sse_connection_and_notification(client):
    """Verifica el flujo SSE: saludo inicial y notificación al publicar lote en ops.data_availability."""
    test_batch_id = str(uuid.uuid4())

    def trigger_availability_update():
        time.sleep(0.5)
        from src.common.db import get_db_connection

        with get_db_connection(role="pipeline") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.data_availability (batch_id, available_at, records_processed, status)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, 'AVAILABLE');
                    """,
                    (test_batch_id, 77),
                )
            conn.commit()

    trigger_thread = threading.Thread(target=trigger_availability_update)
    trigger_thread.start()

    events_received = []
    with client.stream("GET", "/api/v1/events/sse") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line:
                events_received.append(line)
            # Esperamos recibir el evento connected y el evento data_update
            if any("data_update" in l for l in events_received) and any(test_batch_id in l for l in events_received):
                break

    trigger_thread.join()
    assert any("connected" in l for l in events_received)
    assert any("data_update" in l for l in events_received)
    assert any(test_batch_id in l for l in events_received)
