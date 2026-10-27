"""Servicio conversacional del agente de IA para el chatbot de la plataforma.

Obtiene métricas y estadísticas deterministas de la capa Gold y Ops usando
roles de sólo lectura, enriqueciendo el contexto para Ollama o proveyendo
respuestas deterministas precisas ante indisponibilidad del modelo.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field
from src.ai.anomalies import compute_zscore_anomalies_sql
from src.ai.client import AIGenerationResult, OllamaClient, record_ai_execution
from src.ai.prompts import PROMPT_VERSION
from src.ai.reporter import calculate_daily_summary_metrics
from src.common.config import get_settings
from src.common.db import get_db_connection



class ChatMessageItem(BaseModel):
    """Mensaje individual en el historial de conversación."""
    role: str = Field(..., description="Rol del remitente ('user' o 'assistant')")
    content: str = Field(..., min_length=1, description="Contenido textual del mensaje")


class ChatResponse(BaseModel):
    """Respuesta generada por el agente de IA para el chatbot."""
    response: str = Field(..., description="Respuesta en lenguaje natural fundamentada en datos")
    model_name: str = Field(..., description="Nombre del modelo de inferencia o fallback")
    used_fallback: bool = Field(False, description="Indica si se recurrió al motor determinista")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Fecha y hora UTC de la respuesta")



logger = logging.getLogger(__name__)


def build_system_context(metrics: dict[str, Any], anomalies: list[Any], quality: Any) -> str:
    """Construye un prompt de sistema enriquecido con los datos exactos y reglas de la plataforma."""
    max_ev = metrics.get("max_event") or {}
    max_mag = max_ev.get("magnitude", "N/D")
    max_place = max_ev.get("place", "N/D")
    max_depth = max_ev.get("depth_km", "N/D")
    max_time = max_ev.get("time_utc", "N/D")

    top_regs = metrics.get("top_regions", [])
    top_regs_str = ", ".join(
        f"{r['region']} ({r['total_events_24h']} sismos, máx M{r['max_magnitude_24h'] or 'N/D'})"
        for r in top_regs[:5]
    ) or "Sin actividad regional destacada en las últimas 24h"

    dist = metrics.get("magnitude_distribution", [])
    dist_str = ", ".join(f"Rango {d['magnitude_bracket']}: {d['event_count']}" for d in dist) or "Sin datos"

    anom_lines = []
    for a in anomalies[:5]:
        anom_lines.append(f"- Región '{a.region}': {a.event_count} eventos (Z-Score: {a.z_score:.2f}, umbral: {a.threshold})")
    anomalies_str = "\n".join(anom_lines) if anom_lines else "Ninguna anomalía estadística detectada en las últimas 24 horas."

    q_score = quality.get("quality_score", 100.0) if isinstance(quality, dict) else getattr(quality, "quality_score", 100.0)
    q_valid = quality.get("valid_records", 0) if isinstance(quality, dict) else getattr(quality, "valid_records", 0)
    q_total = quality.get("total_records", 0) if isinstance(quality, dict) else getattr(quality, "total_records", 0)
    q_rules = quality.get("failed_rules", {}) if isinstance(quality, dict) else getattr(quality, "failed_rules", {})

    return f"""Eres el Asistente Analítico Inteligente de la Plataforma de Análisis Sísmico USGS.
Tu función es responder preguntas de los usuarios de forma clara, profesional y concisa en español basándote EXCLUSIVAMENTE en los siguientes datos verificados del sistema.

=== DATOS VERIFICADOS DE LA PLATAFORMA (CAPA GOLD / OPS) ===
Periodo analizado: Últimas 24 horas
- Total de sismos registrados: {metrics.get('total_events', 0)}
- Magnitud promedio: {metrics.get('avg_magnitude', 0.0)}
- Alertas de tsunami emitidas: {metrics.get('tsunami_alerts_count', 0)}
- Sismo de mayor magnitud: Magnitud {max_mag} en {max_place} a {max_depth} km de profundidad ({max_time} UTC)
- Regiones con mayor actividad (Top): {top_regs_str}
- Distribución por magnitud: {dist_str}
- Tendencia temporal: {metrics.get('trend', {}).get('direction', 'estable')} ({metrics.get('trend', {}).get('change_percent', 0.0):+1f}%)

Anomalías estadísticas de frecuencia (Z-Score):
{anomalies_str}

Gobernanza y Calidad de datos:
- Puntaje de calidad: {q_score:.1f}% ({q_valid} registros válidos de {q_total} evaluados)
- Reglas infringidas: {q_rules or 'Ninguna'}
=============================================================

REGLAS OBLIGATORIAS:
1. Responde ÚNICAMENTE con base en los datos verificados anteriores. NO inventes cifras, fechas, eventos ni lugares.
2. Si la información solicitada no está en los datos o la consulta excede la plataforma, indícalo claramente con amabilidad.
3. ADVERTENCIA NO PREDICTIVA FUNDAMENTAL: Los sismos NO se pueden predecir. Las estadísticas, conteos y anomalías Z-Score son puramente observacionales e históricas. NUNCA afirmes ni sugieras que se está prediciendo o pronosticando un terremoto futuro.
4. Distingue con claridad entre datos instrumentales medidos (PostgreSQL Gold) y explicaciones analíticas.
5. Sé directo, estructurado y usa formato legible (viñetas si listas datos).
"""


def format_deterministic_chat_response(
    query: str,
    metrics: dict[str, Any],
    anomalies: list[Any],
    quality: Any,
) -> str:
    """Genera una respuesta determinista rigurosa cuando Ollama no está disponible o falla."""
    q_lower = query.lower()
    total = metrics.get("total_events", 0)
    avg_m = metrics.get("avg_magnitude", 0.0)
    max_ev = metrics.get("max_event") or {}
    max_mag = max_ev.get("magnitude", "N/D")
    max_place = max_ev.get("place", "Ubicación no disponible")
    top_regs = metrics.get("top_regions", [])

    if any(k in q_lower for k in ["cuántos", "cuantos", "total", "conteo", "24 horas", "24h", "registrado"]):
        return (
            f"Durante las últimas 24 horas se han consolidado **{total} eventos sísmicos** en la capa Gold "
            f"con una magnitud promedio de **M{avg_m:.2f}** y **{metrics.get('tsunami_alerts_count', 0)}** alertas de tsunami registradas."
        )

    if any(k in q_lower for k in ["mayor magnitud", "más fuerte", "mas fuerte", "máximo", "maximo", "más grande", "mas grande"]):
        return (
            f"El sismo de mayor magnitud en las últimas 24 horas fue de **M{max_mag}**, localizado en **{max_place}**, "
            f"a una profundidad de {max_ev.get('depth_km', 'N/D')} km ocurrido el {max_ev.get('time_utc', 'N/D')} UTC."
        )

    if any(k in q_lower for k in ["región", "region", "regiones", "dónde", "donde", "ranking"]):
        lines = [f"- **{r['region']}**: {r['total_events_24h']} sismos (máx M{r['max_magnitude_24h'] or 'N/D'})" for r in top_regs[:5]]
        regs_text = "\n".join(lines) if lines else "Sin actividad registrada."
        return f"Las regiones con mayor actividad sísmica en las últimas 24 horas son:\n{regs_text}"

    if any(k in q_lower for k in ["anomalía", "anomalia", "atípico", "atipico", "z-score", "zscore", "atención", "atencion"]):
        if anomalies:
            items = [
                f"- **{a.region}**: {a.event_count} sismos observados (Z-Score: {a.z_score:.2f}, umbral: {a.threshold:.1f})"
                for a in anomalies[:5]
            ]
            return (
                f"Se han identificado **{len(anomalies)} anomalías estadísticas** de frecuencia sísmica reciente:\n"
                + "\n".join(items)
                + "\n\n*Nota: Este análisis mide desviaciones estadísticas observadas respecto a la media histórica y no constituye una predicción sísmica.*"
            )
        return (
            "No se han detectado anomalías estadísticas significativas en la frecuencia sísmica durante las últimas 24 horas "
            "(ninguna región superó el umbral Z-Score configurado). Las estadísticas son de naturaleza puramente observacional."
        )

    q_score = quality.get("quality_score", 100.0) if isinstance(quality, dict) else getattr(quality, "quality_score", 100.0)
    q_valid = quality.get("valid_records", 0) if isinstance(quality, dict) else getattr(quality, "valid_records", 0)
    q_total = quality.get("total_records", 0) if isinstance(quality, dict) else getattr(quality, "total_records", 0)
    q_invalid = quality.get("invalid_records", 0) if isinstance(quality, dict) else getattr(quality, "invalid_records", 0)

    if any(k in q_lower for k in ["calidad", "quality", "score", "gobernanza", "reglas"]):
        return (
            f"El estado actual de calidad de los datos es de **{q_score:.1f}%**. "
            f"Se evaluaron **{q_total}** registros, de los cuales **{q_valid}** fueron válidos "
            f"y **{q_invalid}** descartados por incumplimiento de reglas de esquema/coordenadas."
        )

    # Resumen general por defecto
    regs_summary = ", ".join(f"{r['region']} ({r['total_events_24h']})" for r in top_regs[:3])
    return (
        f"**Resumen de actividad sísmica (últimas 24h):**\n"
        f"- **Total de eventos**: {total} sismos (M promedio: {avg_m:.2f}).\n"
        f"- **Evento principal**: M{max_mag} en {max_place}.\n"
        f"- **Zonas destacadas**: {regs_summary or 'Sin datos'}.\n"
        f"- **Calidad de datos**: {q_score:.1f}% de integridad.\n"
        f"- **Anomalías estadísticas**: {len(anomalies)} alertas Z-score vigentes.\n\n"
        f"*Nota: Datos verificados de la capa Gold. La plataforma no realiza predicciones de terremotos.*"
    )



def process_chat_message(message: str, history: Optional[list[ChatMessageItem]] = None) -> ChatResponse:
    """Procesa una consulta del usuario consultando datos reales de Gold e invocando Ollama."""
    settings = get_settings()

    # 1. Obtener datos analíticos verificados de Gold y Ops
    try:
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                metrics = calculate_daily_summary_metrics(cur)
                anomalies = compute_zscore_anomalies_sql(
                    cur=cur,
                    threshold=settings.ai.anomaly_threshold,
                    min_observations=settings.ai.anomaly_min_observations,
                    hours_lookback=24,
                )
                cur.execute(
                    """
                    SELECT quality_score, total_records, valid_records, invalid_records, failed_rules
                    FROM metrics.data_quality
                    ORDER BY evaluated_at DESC
                    LIMIT 1;
                    """
                )
                q_row = cur.fetchone()
                quality = {
                    "quality_score": float(q_row[0]) if q_row else 100.0,
                    "total_records": q_row[1] if q_row else 0,
                    "valid_records": q_row[2] if q_row else 0,
                    "invalid_records": q_row[3] if q_row else 0,
                    "failed_rules": q_row[4] if q_row and isinstance(q_row[4], dict) else {},
                }
    except Exception as db_err:
        logger.error("Error al obtener datos verificados de Gold: %s", db_err)
        return ChatResponse(
            response="No fue posible consultar la base de datos Gold en este momento. Por favor verifique la conexión con la plataforma.",
            model_name="error_handler",
            used_fallback=True,
            timestamp=datetime.now(timezone.utc),
        )

    # 2. Construir el contexto del sistema
    system_prompt = build_system_context(metrics, anomalies, quality)

    # Si hay historial previo, se formatea como contexto conversacional
    full_prompt = message.strip()
    if history:
        recent_history = history[-4:]
        hist_lines = []
        for h in recent_history:
            role_label = "Usuario" if h.role == "user" else "Asistente"
            hist_lines.append(f"{role_label}: {h.content}")
        full_prompt = "Conversación previa:\n" + "\n".join(hist_lines) + f"\n\nPregunta: {message.strip()}"

    # 3. Función de fallback determinista
    def chat_fallback(_data: dict[str, Any]) -> str:
        return format_deterministic_chat_response(message, metrics, anomalies, quality)

    # 4. Invocación a OllamaClient con degradación elegante a fallback
    client = OllamaClient()
    ai_result = client.generate(
        prompt=full_prompt,
        system=system_prompt,
        fallback_fn=chat_fallback,
        fallback_data={"query": message},
    )

    # 5. Registro de auditoría (no bloqueante ante errores)
    try:
        with get_db_connection(role="pipeline") as audit_conn:
            with audit_conn.cursor() as audit_cur:
                record_ai_execution(
                    cur=audit_cur,
                    result=ai_result,
                    automation_type="CHATBOT_INTERACTION",
                    prompt_version=PROMPT_VERSION,
                )
                audit_conn.commit()
    except Exception as audit_err:
        logger.debug("No se pudo registrar la auditoría del chat (no bloqueante): %s", audit_err)

    return ChatResponse(
        response=ai_result.text,
        model_name=ai_result.model_name,
        used_fallback=ai_result.used_fallback,
        timestamp=datetime.now(timezone.utc),
    )
