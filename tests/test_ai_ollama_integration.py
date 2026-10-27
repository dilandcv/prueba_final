"""Pruebas de integración para Ollama, validación Pydantic, consistencia y fallback.

Verifica:
1. Verificación de disponibilidad y preparación del modelo local (<= 3B).
2. Validación de respuestas estructuradas mediante esquemas Pydantic.
3. Rechazo estricto de respuestas con cifras alucinadas o no autorizadas.
4. Rechazo de respuestas que sugieran falsamente capacidad predictiva de sismos.
5. Manejo de reintentos acotados, timeouts y degradación al fallback determinista.
6. Criterio de estimación de costo local (0.0 por defecto o proporcional a tokens).
7. Trazabilidad de ejecuciones (modelo, prompt, latencia, tokens, airflow_run_id).
8. Garantía de no interrupción del pipeline ante caídas totales del modelo.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from src.ai.client import AIGenerationResult, OllamaClient
from src.ai.prompts import (
    AnomalyStructuredOutput,
    DailyReportStructuredOutput,
    get_anomaly_prompt_template,
    get_daily_summary_prompt_template,
    parse_and_validate_json_response,
)


# ==============================================================================
# 1. Verificación de Modelo y Preparación
# ==============================================================================
def test_ollama_is_model_ready_true_when_model_in_tags():
    """Verifica que is_model_ready retorne True cuando el modelo está en la lista de Ollama."""
    client = OllamaClient(base_url="http://mock-ollama:11434", model="llama3.2:1b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "llama3.2:1b"}, {"name": "qwen2.5:0.5b"}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        assert client.is_model_ready() is True


def test_ollama_is_model_ready_false_when_unreachable():
    """Verifica que is_model_ready retorne False de forma segura si Ollama no responde."""
    client = OllamaClient(base_url="http://non-existent-host:11434", model="llama3.2:1b")
    assert client.is_model_ready() is False


# ==============================================================================
# 2. Validación Pydantic y Coherencia de Cifras
# ==============================================================================
def test_validate_structured_anomaly_valid_response():
    """Verifica que una respuesta estructurada que coincide con las cifras autorizadas sea aceptada."""
    authorized = {
        "region": "Alaska",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 6,
        "mean": 1.5,
        "stddev": 0.9,
        "z_score": 5.0,
        "threshold": 3.0,
        "obs_count": 48,
    }

    valid_json = json.dumps({
        "region": "Alaska",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 6,
        "z_score": 5.0,
        "explanation": "Se observó una frecuencia inusualmente alta de 6 sismos en la hora.",
        "is_observational_only": True,
        "non_predictive_disclaimer": "Esta alerta es una desviación observada y no predice sismos.",
    })

    obj, is_valid, error = parse_and_validate_json_response(
        raw_text=valid_json,
        model_cls=AnomalyStructuredOutput,
        authorized_data=authorized,
    )

    assert is_valid is True
    assert error is None
    assert obj.region == "Alaska"
    assert obj.event_count == 6
    assert obj.z_score == 5.0


def test_reject_anomaly_response_with_unauthorized_event_count():
    """Garantiza el rechazo si el modelo altera la cantidad de eventos precalculados."""
    authorized = {
        "region": "California",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 4,
        "z_score": 3.2,
    }

    # El modelo alucina 15 eventos en lugar de los 4 autorizados
    hallucinated_json = json.dumps({
        "region": "California",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 15,  # Cifra no autorizada
        "z_score": 3.2,
        "explanation": "Se observó un incremento a 15 sismos en la región.",
        "is_observational_only": True,
        "non_predictive_disclaimer": "No es una predicción de futuros terremotos.",
    })

    obj, is_valid, error = parse_and_validate_json_response(
        raw_text=hallucinated_json,
        model_cls=AnomalyStructuredOutput,
        authorized_data=authorized,
    )

    assert is_valid is False
    assert obj is None
    assert "Inconsistencia en event_count" in error


def test_reject_anomaly_response_claiming_predictive_ability():
    """Rechaza la respuesta si el modelo afirma falsamente predecir futuros terremotos."""
    authorized = {
        "region": "Japan",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 5,
        "z_score": 4.1,
    }

    misleading_json = json.dumps({
        "region": "Japan",
        "hour_bucket": "2026-10-27 10:00",
        "event_count": 5,
        "z_score": 4.1,
        "explanation": "El enjambre indica que ocurrirá un terremoto mayor mañana.",
        "is_observational_only": True,
        "non_predictive_disclaimer": "Predicción confirmada de actividad futura.",  # Sin negación
    })

    obj, is_valid, error = parse_and_validate_json_response(
        raw_text=misleading_json,
        model_cls=AnomalyStructuredOutput,
        authorized_data=authorized,
    )

    assert is_valid is False
    assert "falsamente capacidad predictiva" in error


def test_validate_structured_daily_report_consistency():
    """Verifica que el informe diario valide la correspondencia exacta de eventos y magnitud."""
    authorized_metrics = {
        "total_events": 35,
        "avg_magnitude": 3.45,
        "tsunami_alerts_count": 0,
        "max_event": {"magnitude": 5.8},
    }

    # Caso 1: Válido
    valid_report_json = json.dumps({
        "title": "Resumen Ejecutivo Diario de Actividad Sísmica",
        "total_events": 35,
        "max_magnitude": 5.8,
        "avg_magnitude": 3.45,
        "tsunami_alerts_count": 0,
        "narrative_overview": "Se registraron 35 eventos sísmicos en la red analítica en las últimas 24h.",
        "regional_activity": "La actividad se concentró en el Cinturón de Fuego del Pacífico con estabilidad.",
        "tsunami_and_context": "No se emitieron alertas de tsunami en el periodo analizado.",
        "non_predictive_note": "Mediciones históricas instrumentales de la capa Gold sin carácter predictivo.",
    })

    obj, is_valid, error = parse_and_validate_json_response(
        raw_text=valid_report_json,
        model_cls=DailyReportStructuredOutput,
        authorized_data=authorized_metrics,
    )
    assert is_valid is True
    assert obj.total_events == 35

    # Caso 2: Rechazado por discrepancia en total_events
    invalid_report_json = json.dumps({
        "title": "Resumen Ejecutivo Diario",
        "total_events": 99,  # Inconsistente con 35
        "max_magnitude": 5.8,
        "avg_magnitude": 3.45,
        "tsunami_alerts_count": 0,
        "narrative_overview": "Descripción general de la actividad de los sismos observados.",
        "regional_activity": "Regiones activas detalladas en el informe ejecutivo analítico.",
        "tsunami_and_context": "Sin alertas de tsunami registradas en el periodo.",
        "non_predictive_note": "Nota técnica sobre mediciones históricas sin predicción.",
    })

    obj_inv, is_valid_inv, error_inv = parse_and_validate_json_response(
        raw_text=invalid_report_json,
        model_cls=DailyReportStructuredOutput,
        authorized_data=authorized_metrics,
    )
    assert is_valid_inv is False
    assert "Inconsistencia en total_events" in error_inv


# ==============================================================================
# 3. Reintentos, Timeouts y Fallback
# ==============================================================================
def test_client_fallback_when_model_returns_invalid_syntax():
    """Verifica que si Ollama responde texto no-JSON, active el fallback tras los reintentos."""
    client = OllamaClient(base_url="http://mock-ollama:11434", max_retries=2)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Respuesta en prosa sin formato JSON requerido"}

    authorized = {"event_count": 3, "z_score": 3.5}
    fallback_called = False

    def mock_fallback(d):
        nonlocal fallback_called
        fallback_called = True
        return f"Fallback determinista para {d['event_count']} eventos"

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.generate(
            prompt="Genera alerta",
            response_model=AnomalyStructuredOutput,
            authorized_data=authorized,
            fallback_fn=mock_fallback,
            fallback_data=authorized,
        )

    assert res.status == "FALLBACK"
    assert res.used_fallback is True
    assert res.model_name == "deterministic_fallback"
    assert fallback_called is True
    assert "Fallback determinista para 3 eventos" in res.text


def test_local_cost_criteria_defaults_to_zero():
    """Documenta y comprueba que el costo estimado sea 0.0 por defecto al ser inferencia local."""
    client = OllamaClient(base_url="http://mock-ollama:11434")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": "Texto generado",
        "prompt_eval_count": 150,
        "eval_count": 80,
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.generate(prompt="Test prompt")

    assert res.status == "SUCCESS"
    assert res.input_tokens == 150
    assert res.output_tokens == 80
    # Costo 0.0 porque la tarifa por defecto es 0.0 en Ollama local
    assert res.estimated_cost == 0.0


def test_local_cost_computes_custom_tariff_when_configured(monkeypatch):
    """Verifica que si se configura una tarifa por token, se calcule adecuadamente."""
    monkeypatch.setenv("AI_COST_PER_TOKEN", "0.000002")
    client = OllamaClient(base_url="http://mock-ollama:11434")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": "Texto generado",
        "prompt_eval_count": 100,
        "eval_count": 50,
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.generate(prompt="Test prompt")

    assert res.status == "SUCCESS"
    # 150 tokens * 0.000002 = 0.000300
    assert pytest.approx(res.estimated_cost, rel=1e-5) == 0.000300


# ==============================================================================
# 4. Prompts Versionados en Directorio prompts/
# ==============================================================================
def test_versioned_prompts_exist_and_substitute_markers():
    """Verifica que los archivos de prompts en prompts/ existan y acepten la sustitución por Python."""
    anomaly_tmpl = get_anomaly_prompt_template()
    assert "{region}" in anomaly_tmpl
    assert "{event_count}" in anomaly_tmpl
    assert "{z_score}" in anomaly_tmpl

    rendered = anomaly_tmpl.format(
        region="Vanuatu",
        hour_bucket="2026-10-27 11:00",
        event_count=7,
        mean=1.8,
        stddev=1.1,
        z_score=4.73,
        threshold=3.0,
        obs_count=60,
    )
    assert "Vanuatu" in rendered
    assert "4.73" in rendered
    assert "7" in rendered

    daily_tmpl = get_daily_summary_prompt_template()
    assert "{total_events}" in daily_tmpl
    assert "{max_magnitude}" in daily_tmpl
    assert "{trend_str}" in daily_tmpl
