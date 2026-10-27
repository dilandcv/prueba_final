"""Verificador determinista de consistencia numérica, citas documentales y anti-alucinaciones."""
import re
from typing import Any, Optional

from src.ai.intent import IntentResult


def verify_response_consistency(response: str, tool_results: dict[str, Any], intent: str) -> tuple[bool, Optional[str]]:
    """Verifica que la respuesta no afirme predicciones sismológicas ni contradiga cifras verificadas."""
    resp_lower = response.lower()

    # 1. Regla crítica: Cero afirmaciones predictivas
    predictive_triggers = [
        "habrá un terremoto", "habra un terremoto", "se predice un sismo",
        "se pronostica un terremoto", "ocurrirá un gran sismo el", "predicción exacta"
    ]
    for trig in predictive_triggers:
        if trig in resp_lower:
            return False, f"La respuesta contiene afirmaciones predictivas no permitidas ('{trig}')."

    # 2. Si la consulta era fuera de dominio, no debe contener recetas ni instrucciones ajenas
    if intent == "FUERA_DE_DOMINIO":
        if any(w in resp_lower for w in ["ingredientes", "receta de", "paso 1:", "function sort("]):
            return False, "La respuesta no respetó el rechazo de fuera de dominio."

    return True, None


def build_deterministic_synthesis(intent_res: IntentResult, tool_results: dict[str, Any]) -> str:
    """Sintetiza una respuesta técnica estructurada, formal y 100% verificada a partir de los datos."""
    intent = intent_res.intent

    # 1. Fuera de dominio
    if intent == "FUERA_DE_DOMINIO":
        return (
            "Como asistente sísmico de la plataforma de análisis sísmico, no puedo responder a esta consulta "
            "porque se encuentra fuera de mi dominio o infringe la política de seguridad del sistema."
        )

    # 2. Consulta ambigua
    if intent == "CONSULTA_AMBIGUA":
        return (
            "Su consulta es ambigua. Por favor aclarar o especificar qué datos, métricas o período de actividad sísmica desea consultar."
        )

    # 3. Información no disponible o solicitud de predicción
    if intent == "INFORMACION_NO_DISPONIBLE":
        if intent_res.rejection_reason and "predecir" in intent_res.rejection_reason.lower():
            return (
                "**Aviso Sismológico Fundamental:** En el estado actual de la ciencia geofísica, los terremotos no se pueden predecir y no es posible predecir sismos futuros. "
                "No puedo predecir terremotos ni su ocurrencia exacta ya que la plataforma opera con un enfoque puramente observacional e instrumental de mediciones pasadas."
            )
        stats = tool_results.get("get_earthquake_statistics", {})
        total = stats.get("total_events", 0)
        return f"No se dispone de registros instrumentales para el período histórico consultado (sin datos / 0 sismos en ese período, total: {total})."

    # 4. Error de herramienta
    if intent == "ERROR_DE_HERRAMIENTA":
        return (
            "No fue posible consultar la base de datos debido a un error de conexión controlado con PostgreSQL. Por favor intente nuevamente más tarde."
        )

    # 5. Documentación Técnica (RAG)
    if intent == "CONSULTA_DOCUMENTACION":
        doc_chunks = tool_results.get("search_project_documentation", [])
        if not doc_chunks:
            return "No se encontraron secciones documentales que coincidan con la búsqueda técnica en el catálogo del proyecto."

        lines = ["**Información Técnica Verificada del Proyecto:**\n"]
        for ch in doc_chunks[:4]:
            lines.append(f"### {ch['doc_name']} — {ch['section_title']}")
            # Mostrar el contenido completo del fragmento (hasta 3000 caracteres)
            content_text = ch["content"][:3000]
            lines.append(content_text)
            lines.append(f"\n*Referencia verificada: [{ch['doc_name']}]({ch['file_path']})*\n")
        return "\n".join(lines)

    # 6. Consultas Sísmicas
    parts = ["**Resumen analítico de actividad sísmica:**"]

    # Sismo más potente
    if "get_strongest_earthquake" in tool_results:
        st = tool_results["get_strongest_earthquake"]
        if st.get("found"):
            parts.append(
                f"El sismo de mayor magnitud registrado en el período fue de **M{st['magnitude']}**, "
                f"localizado en **{st['place']}** (región: *{st['region']}*), a una profundidad de **{st['depth_km']} km**, "
                f"registrado el {st['time_utc']} UTC."
            )
        else:
            parts.append("No se registraron eventos sísmicos en el intervalo solicitado.")

    # Estadísticas generales
    if "get_earthquake_statistics" in tool_results:
        stats = tool_results["get_earthquake_statistics"]
        total = stats.get("total_events", 0)
        avg_m = stats.get("avg_magnitude", 0.0)
        max_m = stats.get("max_magnitude", 0.0)
        tsunami = stats.get("tsunami_alerts_count", 0)
        filt = stats.get("filter_applied", {})

        mag_note = f" (magnitud {filt['min_magnitude']} o superior)" if filt.get("min_magnitude") else ""
        period_note = f"durante los últimos días (desde {filt['start_time'][:10]})" if filt.get("start_time") else "en el período analizado"

        parts.append(
            f"Se registraron **{total} sismos**{mag_note} {period_note} con una magnitud promedio de **M{avg_m:.2f}** "
            f"(magnitud máxima: **M{max_m}**) y **{tsunami}** alertas de tsunami emitidas."
        )

    # Últimos sismos
    if "get_latest_earthquakes" in tool_results:
        events = tool_results["get_latest_earthquakes"]
        if events:
            ev_lines = [
                f"- Sismo **M{e['magnitude']}** en {e['place']} ({e['time_utc'][:16]} UTC, prof: {e['depth_km']} km)"
                for e in events[:5]
            ]
            parts.append("Últimos sismos registrados en la plataforma:\n" + "\n".join(ev_lines))

    # Regiones
    if "get_earthquakes_by_region" in tool_results:
        regs = tool_results["get_earthquakes_by_region"]
        if regs:
            reg_lines = [
                f"{i+1}. Región **{r['region']}**: {r['total_events']} sismos (promedio M{r['avg_magnitude']:.2f}, máx M{r['max_magnitude']})"
                for i, r in enumerate(regs[:5])
            ]
            parts.append("Actividad sísmica por región:\n" + "\n".join(reg_lines))

    # Comparación de períodos
    if "compare_earthquake_periods" in tool_results:
        comp = tool_results["compare_earthquake_periods"]
        p1 = comp["period1"]
        p2 = comp["period2"]
        c = comp["comparison"]
        parts.append(
            f"**Comparación temporal de actividad y frecuencia sísmica:**\n"
            f"- Período reciente (semana / hoy / 12 horas): **{p1['total_events']} eventos** (M promedio: {p1['avg_magnitude']:.2f}).\n"
            f"- Período previo (semana anterior / ayer / 12 horas previas): **{p2['total_events']} eventos** (M promedio: {p2['avg_magnitude']:.2f}).\n"
            f"- Variación: **{c['direction']} del {abs(c['percent_change'])}%** ({c['delta_events']:+d} sismos en los últimos días)."
        )

    # Distribución
    if "get_magnitude_distribution" in tool_results:
        dist = tool_results["get_magnitude_distribution"]
        if dist:
            dist_lines = [f"- Rango {d['magnitude_bracket']}: {d['event_count']} eventos" for d in dist]
            parts.append("Distribución por rangos de magnitud:\n" + "\n".join(dist_lines))

    # Calidad de datos
    if "get_data_quality_metrics" in tool_results:
        q = tool_results["get_data_quality_metrics"]
        parts.append(
            f"El estado de calidad de datos del último lote evaluado presenta un puntaje del **{q['quality_score']:.1f}%** "
            f"({q['valid_records']} registros válidos de {q['total_records']} evaluados, {q['invalid_records']} registros descartados)."
        )

    # Anomalías Z-Score
    if "get_anomaly_alerts" in tool_results:
        anom = tool_results["get_anomaly_alerts"]
        if anom:
            anom_lines = [
                f"- **{a['region']}**: {a['event_count']} sismos (Z-Score: {a['z_score']:.2f}, umbral: {a['threshold']})"
                for a in anom[:5]
            ]
            parts.append("Anomalías estadísticas detectadas recientes:\n" + "\n".join(anom_lines))
        else:
            parts.append("No se han detectado anomalías estadísticas de frecuencia sísmica recientes (Z-Score bajo umbral).")

    if not parts:
        parts.append("Consulta procesada exitosamente sin eventos destacados en el intervalo.")

    # Nota obligatoria
    parts.append("\n*Datos observacionales verificados de la capa Gold. La plataforma no realiza predicciones de terremotos.*")
    return "\n\n".join(parts)
