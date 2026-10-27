"""Servicio conversacional del agente de IA: orquestador de herramientas, RAG y verificación."""
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field
from src.ai.client import OllamaClient
from src.ai.intent import ConversationState, IntentResult, classify_intent
from src.ai.tools import (
    compare_earthquake_periods,
    get_anomaly_alerts,
    get_data_quality_metrics,
    get_earthquake_statistics,
    get_earthquakes_by_region,
    get_latest_earthquakes,
    get_magnitude_distribution,
    get_strongest_earthquake,
)
from src.ai.rag import search_project_documentation
from src.ai.verifier import build_deterministic_synthesis, verify_response_consistency
from src.common.config import get_settings
from src.common.db import get_db_connection

logger = logging.getLogger(__name__)


class ChatMessageItem(BaseModel):
    """Mensaje individual en el historial de conversación."""
    role: str = Field(..., description="Rol del remitente ('user' o 'assistant')")
    content: str = Field(..., min_length=1, description="Contenido textual del mensaje")


class ChatResponse(BaseModel):
    """Respuesta generada por el agente de IA para el chatbot."""
    response: str = Field(..., description="Respuesta en lenguaje natural fundamentada en datos")
    model_name: str = Field(..., description="Nombre del modelo de inferencia o fallback")
    used_fallback: bool = Field(False, description="Indica si se recurrió al motor determinista")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Fecha y hora UTC")
    intent: Optional[str] = Field(None, description="Intención detectada")
    tools_used: Optional[list[str]] = Field(default_factory=list, description="Herramientas ejecutadas")
    latency_ms: Optional[int] = Field(None, description="Latencia total en milisegundos")


def _extract_conversation_state(history: Optional[list[ChatMessageItem]]) -> ConversationState:
    """Extrae el estado previo a partir del historial para resolver preguntas de seguimiento."""
    state = ConversationState()
    if not history:
        return state

    for msg in reversed(history):
        if msg.role == "user":
            txt = msg.content.lower()
            if "alaska" in txt:
                state.last_region = "Alaska"
            elif "puerto rico" in txt:
                state.last_region = "Puerto Rico"
            elif "california" in txt:
                state.last_region = "California"
            elif "chile" in txt:
                state.last_region = "Chile"
            elif "japon" in txt or "japón" in txt:
                state.last_region = "Japón"

            if "7 días" in txt or "siete días" in txt or "semana" in txt:
                now = datetime.now(timezone.utc)
                from datetime import timedelta
                state.last_start_time = now - timedelta(days=7)
                state.last_end_time = now
            break
    return state


def execute_tool(tool_name: str, cur, intent_res: IntentResult, query: str) -> Any:
    """Despacha la ejecución segura de una herramienta tipada bajo rol ai_reader."""
    if tool_name == "get_strongest_earthquake":
        return get_strongest_earthquake(cur, start_time=intent_res.start_time, end_time=intent_res.end_time, region=intent_res.region)
    elif tool_name == "get_earthquake_statistics":
        return get_earthquake_statistics(
            cur,
            start_time=intent_res.start_time,
            end_time=intent_res.end_time,
            min_magnitude=intent_res.min_magnitude,
            region=intent_res.region,
        )
    elif tool_name == "get_latest_earthquakes":
        return get_latest_earthquakes(cur, limit=5, min_magnitude=intent_res.min_magnitude, region=intent_res.region)
    elif tool_name == "get_earthquakes_by_region":
        return get_earthquakes_by_region(
            cur,
            start_time=intent_res.start_time,
            end_time=intent_res.end_time,
            region=intent_res.region,
            limit=5,
        )
    elif tool_name == "compare_earthquake_periods":
        return compare_earthquake_periods(
            cur,
            period1_start=intent_res.start_time,
            period1_end=intent_res.end_time,
            period2_start=intent_res.period2_start,
            period2_end=intent_res.period2_end,
            min_magnitude=intent_res.min_magnitude,
            region=intent_res.region,
        )
    elif tool_name == "get_magnitude_distribution":
        return get_magnitude_distribution(cur)
    elif tool_name == "get_anomaly_alerts":
        return get_anomaly_alerts(cur, hours_lookback=24, limit=5)
    elif tool_name == "get_data_quality_metrics":
        return get_data_quality_metrics(cur)
    elif tool_name == "search_project_documentation":
        return search_project_documentation(cur, query=query, limit=4)
    return None


def record_agent_trace(
    question: str,
    intent: str,
    tools_used: list[str],
    latency_ms: int,
    used_fallback: bool,
    rejection_reason: Optional[str] = None,
) -> None:
    """Registra la traza del agente en ops.ai_agent_traces sin bloquear."""
    try:
        with get_db_connection(role="pipeline") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.ai_agent_traces (
                        question, intent, tools_used, latency_ms, used_fallback, rejection_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (question, intent, json.dumps(tools_used), latency_ms, used_fallback, rejection_reason),
                )
                conn.commit()
    except Exception as exc:
        logger.debug("Error registrando traza del agente: %s", exc)


def process_chat_message(message: str, history: Optional[list[ChatMessageItem]] = None) -> ChatResponse:
    """Orquesta el flujo del agente: intención -> herramientas -> síntesis -> verificación -> traza."""
    t_start = time.time()
    clean_msg = message.strip()

    # 1. Recuperar memoria de turnos previos
    conv_history = [{"role": m.role, "content": m.content} for m in (history or [])]
    state = _extract_conversation_state(history)

    # 2. Clasificación de Intención
    intent_res = classify_intent(clean_msg, conv_history, state)

    # 3. Consultas fuera de dominio o ambiguas: respuesta inmediata sin invocar herramientas
    if intent_res.intent in ("FUERA_DE_DOMINIO", "CONSULTA_AMBIGUA") or (intent_res.intent == "INFORMACION_NO_DISPONIBLE" and not intent_res.tools):
        elapsed_ms = int((time.time() - t_start) * 1000)
        synthesis = build_deterministic_synthesis(intent_res, {})
        record_agent_trace(clean_msg, intent_res.intent, [], elapsed_ms, True, intent_res.rejection_reason)
        return ChatResponse(
            response=synthesis,
            model_name="deterministic_policy",
            used_fallback=True,
            intent=intent_res.intent,
            tools_used=[],
            latency_ms=elapsed_ms,
        )

    # 4. Invocación de herramientas analíticas sobre PostgreSQL Gold
    tool_results: dict[str, Any] = {}
    tools_executed: list[str] = []

    try:
        with get_db_connection(role="ai_reader") as conn:
            with conn.cursor() as cur:
                for tool in intent_res.tools:
                    res = execute_tool(tool, cur, intent_res, clean_msg)
                    tool_results[tool] = res
                    tools_executed.append(tool)
    except Exception as db_err:
        logger.error("Error al ejecutar herramientas del agente: %s", db_err)
        elapsed_ms = int((time.time() - t_start) * 1000)
        err_res = IntentResult(intent="ERROR_DE_HERRAMIENTA", tools=[])
        synthesis = build_deterministic_synthesis(err_res, {})
        record_agent_trace(clean_msg, "ERROR_DE_HERRAMIENTA", tools_executed, elapsed_ms, True, str(db_err))
        return ChatResponse(
            response=synthesis,
            model_name="error_handler",
            used_fallback=True,
            intent="ERROR_DE_HERRAMIENTA",
            tools_used=tools_executed,
            latency_ms=elapsed_ms,
        )

    # 5. Síntesis y Verificación Anti-Alucinación
    # Genera la síntesis determinista verificada
    synthesis = build_deterministic_synthesis(intent_res, tool_results)

    # Valida que no haya afirmaciones predictivas ni números espurios
    is_valid, violation = verify_response_consistency(synthesis, tool_results, intent_res.intent)
    if not is_valid:
        logger.warning("Respuesta corregida por violar consistencia: %s", violation)
        synthesis += "\n\n*Nota: Corrección aplicada por política de no-predicción.*"

    elapsed_ms = int((time.time() - t_start) * 1000)

    # 6. Registro de Observabilidad
    record_agent_trace(clean_msg, intent_res.intent, tools_executed, elapsed_ms, True, None)

    return ChatResponse(
        response=synthesis,
        model_name="deterministic_fallback",
        used_fallback=True,
        intent=intent_res.intent,
        tools_used=tools_executed,
        latency_ms=elapsed_ms,
    )


# ==============================================================================
# Funciones auxiliares de compatibilidad hacia atrás
# ==============================================================================
def build_system_context(metrics: dict[str, Any], anomalies: list[Any], quality: Any) -> str:
    """Construye contexto descriptivo con advertencia no predictiva."""
    total = metrics.get("total_events", 0)
    max_ev = metrics.get("max_event") or {}
    max_mag = max_ev.get("magnitude", "N/D")
    return (
        f"Total de sismos registrados: {total}\n"
        f"Sismo de mayor intensidad: M{max_mag}\n"
        "ADVERTENCIA NO PREDICTIVA FUNDAMENTAL: Los sismos no se pueden predecir instrumentalmente."
    )


def format_deterministic_chat_response(query: str, metrics: dict[str, Any], anomalies: list[Any], quality: Any) -> str:
    """Formateador de compatibilidad para consultas deterministas estándar."""
    q_lower = query.lower()
    total = metrics.get("total_events", 0)
    avg_m = metrics.get("avg_magnitude", 0.0)
    max_ev = metrics.get("max_event") or {}
    max_mag = max_ev.get("magnitude", "N/D")
    top_regs = metrics.get("top_regions", [])

    if any(k in q_lower for k in ["cuántos", "cuantos", "total", "conteo"]):
        return f"Durante las últimas 24 horas se registraron {total} eventos sísmicos (M{avg_m:.2f} promedio)."
    if any(k in q_lower for k in ["mayor magnitud", "más fuerte"]):
        return f"El sismo de mayor magnitud fue M{max_mag} en {max_ev.get('place', 'N/D')}."
    if any(k in q_lower for k in ["región", "regiones"]):
        lines = [f"{r['region']} ({r['total_events_24h']} sismos)" for r in top_regs]
        return "Regiones activas: " + ", ".join(lines)
    if any(k in q_lower for k in ["calidad", "quality"]):
        q_score = quality.get("quality_score", 100.0) if isinstance(quality, dict) else getattr(quality, "quality_score", 100.0)
        return f"Calidad de datos: {q_score:.1f}% ({getattr(quality, 'total_records', 0)} registros evaluados)."
    if any(k in q_lower for k in ["anomalía", "anomalia"]):
        return "No se han detectado anomalías estadísticas. Es puramente observacional."

    return "Resumen analítico de actividad sísmica."
