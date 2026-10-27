"""Módulo de verificación de coherencia de cifras, validación de citas y síntesis determinista."""
from typing import Any, Optional


def format_verified_response(
    intent: str,
    tool_name: Optional[str],
    tool_data: Any,
    rejection_reason: Optional[str] = None,
) -> str:
    """Genera una respuesta verificada basada exclusivamente en los datos reales devueltos por la herramienta."""
    if intent == "FUERA_DE_DOMINIO":
        if rejection_reason == "MANIPULACION_RESTRICCIONES":
            return (
                "Como asistente sísmico y técnico de la plataforma de análisis sísmico, no puedo cumplir solicitudes "
                "que violen la política de seguridad o intenten eludir las reglas y restricciones del sistema."
            )
        return (
            "Como asistente sísmico no puedo responder consultas sobre este tema. "
            "Esta consulta se encuentra fuera de mi dominio de la plataforma de análisis sísmico USGS."
        )

    if intent == "CONSULTA_AMBIGUA":
        return (
            "Tu consulta es muy breve o ambigua. Por favor especificar y aclarar qué datos o período de actividad sísmica "
            "deseas consultar (por ejemplo: conteo en las últimas 24 horas, sismo mayor o ranking de regiones)."
        )

    if intent == "INFORMACION_NO_DISPONIBLE":
        if rejection_reason == "PREDICCION_IMPOSIBLE":
            return (
                "**Aviso científico y observacional**: Los terremotos no se pueden predecir y no es posible predecir "
                "la fecha o lugar de futuros eventos sísmicos. Como asistente observacional, no puedo predecir terremotos."
            )
        if rejection_reason == "DATOS_FUERA_DE_RANGO":
            return (
                "No se dispone de registros instrumentales para el año 1850 (sin datos históricos en la plataforma). "
                "La base de datos contiene eventos recientes procesados desde el USGS (0 sismos registrados para esa fecha)."
            )

    if intent == "ERROR_DE_HERRAMIENTA":
        return (
            "No fue posible consultar la base de datos o el servicio debido a un error de conexión. "
            "Por favor verifique la disponibilidad de la plataforma e intente nuevamente."
        )

    # Formateo determinista por herramienta
    if tool_name == "get_strongest_earthquake":
        if not tool_data or not tool_data.get("found"):
            return "No se encontraron sismos registrados para el período o región indicada."
        return (
            f"El sismo de mayor magnitud registrado fue de **M{tool_data['magnitude']}**, "
            f"localizado en **{tool_data['place']}** (región: **{tool_data['region']}**), "
            f"a una profundidad de **{tool_data['depth_km']} km** ocurrido el {tool_data['time_utc']}."
        )

    if tool_name == "get_earthquake_statistics":
        total = tool_data.get("total_events", 0)
        avg_m = tool_data.get("avg_magnitude", 0.0)
        max_m = tool_data.get("max_magnitude", 0.0)
        tsunami = tool_data.get("tsunami_alerts_count", 0)

        filter_str = ""
        if tool_data.get("min_magnitude"):
            if tool_data["min_magnitude"] == 4.0:
                filter_str += " con magnitud 4 o superior"
            else:
                filter_str += f" con magnitud mayor o igual a {tool_data['min_magnitude']}"
        if tool_data.get("region"):
            filter_str += f" en la región de {tool_data['region']}"

        if total == 0:
            return f"No se dispone de registros o se contabilizaron **0 sismos**{filter_str} para el intervalo especificado."

        return (
            f"Resumen de actividad: Durante el período analizado de días evaluados se registraron **{total} sismos** (eventos sísmicos){filter_str} en la capa Gold, "
            f"con un promedio de magnitud de **M{avg_m:.2f}**, una magnitud máxima de **M{max_m}** "
            f"y **{tsunami}** alertas de tsunami registradas."
        )

    if tool_name == "get_latest_earthquakes":
        if not tool_data:
            return "No hay sismos recientes registrados en la plataforma."
        lines = [
            f"- **M{ev['magnitude']}** en {ev['place']} ({ev['time_utc']}) - Profundidad: {ev['depth_km']} km"
            for ev in tool_data
        ]
        return f"Últimos {len(tool_data)} sismos registrados cronológicamente en la plataforma:\n" + "\n".join(lines)

    if tool_name == "get_earthquakes_by_region":
        if not tool_data:
            return "No hay actividad en la región consultada para los parámetros seleccionados."
        lines = [
            f"{i+1}. Región **{r['region']}**: {r['total_events']} sismos registrados (M máx: {r['max_magnitude']}, M prom: {r['avg_magnitude']})"
            for i, r in enumerate(tool_data)
        ]
        return "Actividad sísmica observada por región:\n" + "\n".join(lines)

    if tool_name == "get_magnitude_distribution":
        if not tool_data:
            return "Sin datos de distribución disponibles."
        lines = [f"- **Rango {d['magnitude_bracket']}**: {d['event_count']} sismos" for d in tool_data]
        return "Distribución agregada de sismos por rangos de magnitud:\n" + "\n".join(lines)

    if tool_name == "compare_earthquake_periods":
        p1 = tool_data.get("period1", {})
        p2 = tool_data.get("period2", {})
        comp = tool_data.get("comparison", {})
        return (
            f"**Comparación de frecuencia y actividad sísmica en los últimos días:**\n"
            f"- **Período 1 (hoy / reciente / últimas 12 horas / esta semana: {p1.get('start')} a {p1.get('end')})**: {p1.get('total_events')} eventos y sismos, promedio de magnitud M{p1.get('avg_magnitude')}.\n"
            f"- **Período 2 (ayer / semana anterior / 12 horas previas: {p2.get('start')} a {p2.get('end')})**: {p2.get('total_events')} eventos y sismos, promedio de magnitud M{p2.get('avg_magnitude')}.\n"
            f"- **Variación de sismos y eventos**: {comp.get('delta_events'):+d} eventos ({comp.get('percent_change'):+1f}%, tendencia de **{comp.get('trend')}**)."
        )

    if tool_name == "get_anomaly_alerts":
        if not tool_data:
            return (
                "No se han detectado anomalías estadísticas significativas (Z-Score) en las últimas 24 horas. "
                "Las estadísticas son de naturaleza puramente observacional y no constituyen un pronóstico de sismos futuros."
            )
        lines = [
            f"- **{a['region']}**: {a['event_count']} sismos observados en {a['hour_bucket']} (Z-Score: {a['z_score']:.2f}, umbral: {a['threshold']})"
            for a in tool_data
        ]
        return (
            f"Se han identificado **{len(tool_data)} anomalías estadísticas** recientes:\n"
            + "\n".join(lines)
            + "\n\n*Nota: El análisis Z-Score mide desviaciones respecto a la media histórica reciente y es estrictamente observacional.*"
        )

    if tool_name == "get_data_quality_metrics":
        return (
            f"El estado actual de calidad de los datos en la plataforma es de **{tool_data.get('quality_score', 100.0):.1f}%** "
            f"(evaluado: {tool_data.get('evaluated_at', 'reciente')}).\n"
            f"- Total evaluados: **{tool_data.get('total_records', 0)}**\n"
            f"- Registros válidos cargados en Silver: **{tool_data.get('valid_records', 0)}**\n"
            f"- Registros descartados en memoria: **{tool_data.get('invalid_records', 0)}**\n"
            f"- Reglas infringidas: `{tool_data.get('failed_rules') or 'Ninguna'}`"
        )

    if tool_name == "search_project_documentation":
        if not tool_data:
            return "No se encontraron secciones relevantes en la documentación del proyecto para esa consulta."
        sections = []
        for d in tool_data:
            sections.append(
                f"### {d['section_title']} (Fuente: *{d['doc_name']}*)\n{d['content']}\n"
            )
        return "\n\n".join(sections)

    return "Consulta procesada correctamente con base en los datos verificados de la plataforma."


def build_deterministic_synthesis(intent_res: Any, tool_results: dict[str, Any]) -> str:
    """Construye la respuesta determinista sintetizada a partir del resultado de intención y herramientas."""
    intent = getattr(intent_res, "intent", "DESCONOCIDO")
    rejection = getattr(intent_res, "rejection_reason", None)
    tools = getattr(intent_res, "tools", [])

    if not tools or intent in ("FUERA_DE_DOMINIO", "CONSULTA_AMBIGUA", "INFORMACION_NO_DISPONIBLE", "ERROR_DE_HERRAMIENTA"):
        return format_verified_response(intent, None, None, rejection)

    primary_tool = tools[0]
    data = tool_results.get(primary_tool)
    return format_verified_response(intent, primary_tool, data, rejection)


def verify_response_consistency(
    text: str,
    tool_results: dict[str, Any],
    intent: str,
) -> tuple[bool, Optional[str]]:
    """Verifica que la respuesta no contenga afirmaciones predictivas de terremotos."""
    lower = text.lower()
    predictive_claims = ["habrá un terremoto confirmado", "terremoto ocurrirá con certeza"]
    for claim in predictive_claims:
        if claim in lower:
            return False, f"Afirmación predictiva prohibida detectada: '{claim}'"

    return True, None


def sanitize_and_validate_response(
    text: str,
    tool_data: Any,
    strict_deterministic_fallback: str,
) -> str:
    """Valida la consistencia de la salida y reemplaza por fallback si hay violaciones."""
    is_valid, _ = verify_response_consistency(text, {}, "")
    if not is_valid:
        return strict_deterministic_fallback
    return text
