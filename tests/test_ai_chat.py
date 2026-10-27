"""Pruebas para el servicio conversacional y el endpoint /api/v1/ai/chat."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from src.ai.chat_service import (
    build_system_context,
    format_deterministic_chat_response,
    process_chat_message,
)
from src.api.main import app
from src.api.schemas import QualitySummaryResponse


client = TestClient(app)


def test_build_system_context_contains_non_predictive_warning():
    """Garantiza que el contexto del sistema incluya la advertencia obligatoria de no-predicción."""
    mock_metrics = {
        "total_events": 25,
        "avg_magnitude": 3.4,
        "tsunami_alerts_count": 0,
        "max_event": {"magnitude": 5.1, "place": "Test Region", "time_utc": "2026-10-27 10:00", "depth_km": 10.0},
        "top_regions": [{"region": "Chile", "total_events_24h": 5, "max_magnitude_24h": 5.1}],
        "magnitude_distribution": [{"magnitude_bracket": "3.0 - 3.9", "event_count": 10}],
        "trend": {"direction": "estable", "change_percent": 0.0},
    }
    mock_quality = QualitySummaryResponse(
        quality_score=99.5,
        total_records=100,
        valid_records=99,
        invalid_records=1,
        failed_rules={"rule_magnitude_valid": 1},
        evaluated_at=None,
    )

    ctx = build_system_context(mock_metrics, [], mock_quality)
    assert "Total de sismos registrados: 25" in ctx
    assert "M5.1" in ctx or "5.1" in ctx
    assert "ADVERTENCIA NO PREDICTIVA" in ctx or "no se pueden predecir" in ctx.lower()


def test_deterministic_chat_response_categories():
    """Comprueba que el motor de fallback determinista responda fielmente según el tipo de consulta."""
    mock_metrics = {
        "total_events": 42,
        "avg_magnitude": 3.85,
        "tsunami_alerts_count": 1,
        "max_event": {"magnitude": 6.2, "place": "Near Coast of Japan", "time_utc": "2026-10-27 08:30", "depth_km": 15.0},
        "top_regions": [{"region": "Japan", "total_events_24h": 12, "max_magnitude_24h": 6.2}],
        "magnitude_distribution": [],
    }
    mock_quality = QualitySummaryResponse(
        quality_score=100.0,
        total_records=50,
        valid_records=50,
        invalid_records=0,
        failed_rules={},
        evaluated_at=None,
    )

    # 1. Conteo / 24h
    r_count = format_deterministic_chat_response("¿Cuántos sismos se registraron en las últimas 24 horas?", mock_metrics, [], mock_quality)
    assert "42 eventos sísmicos" in r_count
    assert "M3.85" in r_count

    # 2. Magnitud máxima
    r_max = format_deterministic_chat_response("¿Cuál fue el sismo de mayor magnitud?", mock_metrics, [], mock_quality)
    assert "M6.2" in r_max
    assert "Near Coast of Japan" in r_max

    # 3. Regiones
    r_regs = format_deterministic_chat_response("¿Qué regiones presentan más actividad sísmica?", mock_metrics, [], mock_quality)
    assert "Japan" in r_regs
    assert "12 sismos" in r_regs

    # 4. Calidad
    r_qual = format_deterministic_chat_response("¿Cuál es el estado de la calidad de los datos?", mock_metrics, [], mock_quality)
    assert "100.0%" in r_qual
    assert "50" in r_qual

    # 5. Anomalías
    r_anom = format_deterministic_chat_response("¿Se han detectado anomalías recientes?", mock_metrics, [], mock_quality)
    assert "No se han detectado anomalías estadísticas" in r_anom
    assert "observacional" in r_anom.lower()


def test_api_chat_endpoint_success():
    """Verifica que el endpoint /api/v1/ai/chat responda exitosamente vía HTTP."""
    resp = client.post("/api/v1/ai/chat", json={"message": "¿Cuántos sismos se han registrado?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert len(data["response"]) > 10
    assert "model_name" in data
    assert "used_fallback" in data


def test_api_chat_endpoint_validation():
    """Verifica el rechazo de mensajes vacíos o con estructura inválida."""
    resp = client.post("/api/v1/ai/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_fallback_when_ollama_fails():
    """Verifica la degradación transparente al fallback determinista cuando Ollama falla."""
    with patch("httpx.Client.post", side_effect=Exception("Connection refused to Ollama")):
        resp = process_chat_message(message="¿Cuál ha sido el sismo de mayor magnitud?")
        assert resp.used_fallback is True
        assert "M" in resp.response
        assert resp.model_name == "deterministic_fallback"
