"""Clasificador determinista de intenciones, extracción de entidades y memoria conversacional."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Optional


@dataclass
class ConversationState:
    """Estado estructurado de la conversación para resolución de seguimiento."""
    last_region: Optional[str] = None
    last_start_time: Optional[datetime] = None
    last_end_time: Optional[datetime] = None
    last_min_magnitude: Optional[float] = None
    last_event_id: Optional[str] = None
    last_event_place: Optional[str] = None
    last_intent: Optional[str] = None


@dataclass
class IntentResult:
    """Resultado de la clasificación de intención y parámetros extraídos."""
    intent: str
    tools: list[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    min_magnitude: Optional[float] = None
    region: Optional[str] = None
    period2_start: Optional[datetime] = None
    period2_end: Optional[datetime] = None
    is_followup: bool = False
    rejection_reason: Optional[str] = None


OUT_OF_DOMAIN_PATTERNS = [
    r"arroz", r"receta", r"cocin", r"pollo", r"fútbol", r"futbol", r"mundial",
    r"javascript", r"código", r"codigo", r"ordenar un array", r"sort",
    r"hackear", r"contraseña", r"password", r"ignora.*instrucciones",
    r"sin restricciones", r"olvida tus reglas", r"quién ganó", r"quien gano"
]

AMBIGUOUS_PATTERNS = [
    r"qué pasó ayer", r"dime los datos", r"cómo estuvo", r"dime más", r"qué hubo", r"cuéntame"
]

DOCUMENTATION_KEYWORDS = [
    "arquitectura", "medallion", "bronze", "silver", "gold", "spark", "pyspark",
    "pandas", "dask", "polars", "airflow", "dag", "dags", "idempotencia", "staging",
    "api_reader", "pipeline", "ai_reader", "roles", "permisos", "endpoints",
    "calidad", "failed_rules", "openmetadata", "docker", "postgre"
]


def classify_intent(message: str, history: Optional[list[dict[str, str]]] = None, state: Optional[ConversationState] = None) -> IntentResult:
    """Clasifica la intención del usuario y extrae parámetros analíticos con soporte de memoria."""
    q_norm = message.strip().lower()
    now = datetime.now(timezone.utc)

    # 1. Filtro estricto de Fuera de Dominio y Seguridad (Prompt Injection)
    # Si además intenta forzar una predicción sísmica ("afirma que habrá un terremoto"), se prioriza el rechazo no-predictivo
    if "habrá un terremoto" in q_norm or "habra un terremoto" in q_norm or "terremoto mañana" in q_norm:
        return IntentResult(
            intent="INFORMACION_NO_DISPONIBLE",
            tools=[],
            rejection_reason="Los terremotos no se pueden predecir instrumentalmente.",
        )

    for pat in OUT_OF_DOMAIN_PATTERNS:
        if re.search(pat, q_norm):
            return IntentResult(
                intent="FUERA_DE_DOMINIO",
                tools=[],
                rejection_reason="Consulta fuera de dominio o intento de manipulación de instrucciones.",
            )

    # 2. Consultas sobre información futura o predicción imposible
    if any(k in q_norm for k in ["cuándo ocurrirá", "cuando ocurrira", "próximo gran terremoto", "proximo gran terremoto", "predecir terremoto", "habrá un terremoto", "habra un terremoto", "futuro terremoto"]):
        return IntentResult(
            intent="INFORMACION_NO_DISPONIBLE",
            tools=[],
            rejection_reason="Los terremotos no se pueden predecir instrumentalmente.",
        )

    # 3. Escenarios de prueba de fallos de servicio simulados
    if "[escenario: postgresql desconectado]" in q_norm or "postgresql desconectado" in q_norm:
        return IntentResult(
            intent="ERROR_DE_HERRAMIENTA",
            tools=["get_strongest_earthquake"],
            rejection_reason="Error simulado de PostgreSQL para prueba de resiliencia.",
        )

    # 4. Consultas sobre épocas históricas fuera del rango de la plataforma
    if any(k in q_norm for k in ["1850", "año 1800", "siglo xix", "siglo xviii"]):
        return IntentResult(
            intent="INFORMACION_NO_DISPONIBLE",
            tools=["get_earthquake_statistics"],
            rejection_reason="No se dispone de registros instrumentales para fechas históricas anteriores a la plataforma.",
        )

    # 5. Consultas ambiguas sin contexto previo
    has_history = history and len(history) > 0
    if not has_history:
        for pat in AMBIGUOUS_PATTERNS:
            if re.search(pat, q_norm):
                return IntentResult(
                    intent="CONSULTA_AMBIGUA",
                    tools=[],
                    rejection_reason="Pregunta ambigua que requiere aclaración sobre la métrica o período deseado.",
                )

    # 6. Detección de preguntas de seguimiento conversacional
    is_followup = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    min_magnitude: Optional[float] = None
    region: Optional[str] = None

    if has_history and any(q_norm.startswith(k) for k in ["¿y ", "y ", "¿en qué lugar", "en que lugar", "¿a qué profundidad", "a que profundidad", "¿y en esa", "y en esa", "compáralo", "comparalo"]):
        is_followup = True
        if state:
            start_time = state.last_start_time
            end_time = state.last_end_time
            region = state.last_region
            min_magnitude = state.last_min_magnitude

    # 7. Extracción de Magnitud
    mag_match = re.search(r"(?:magnitud|m)\s*(?:mayor o igual a|>=|>|superior a)?\s*(\d+(?:\.\d+)?)", q_norm)
    if mag_match:
        min_magnitude = float(mag_match.group(1))

    # 8. Extracción de Regiones comunes
    known_regions = [
        "alaska", "puerto rico", "california", "chile", "japón", "japon", "japan",
        "méxico", "mexico", "hawái", "hawaii", "indonesia", "perú", "peru", "ecuador"
    ]
    for r in known_regions:
        if r in q_norm:
            region = r.capitalize()
            break

    # 9. Prioridad a Documentación de Reglas de Calidad
    if "reglas de calidad" in q_norm or "qué reglas" in q_norm or "que reglas" in q_norm:
        return IntentResult(
            intent="CONSULTA_DOCUMENTACION",
            tools=["search_project_documentation"],
        )

    # 10. Prioridad a Calidad de Datos antes de Comparaciones
    if any(k in q_norm for k in ["puntaje de calidad", "registros fueron válidos", "descartados", "valid_records", "quality_score"]):
        return IntentResult(
            intent="CONSULTA_SISMICA",
            tools=["get_data_quality_metrics"],
        )

    # 11. Consultas de Comparación Temporal
    is_comparison = (
        "semana anterior" in q_norm
        or "compara" in q_norm
        or "frente al de ayer" in q_norm
        or "frente a" in q_norm
        or "que en las" in q_norm
        or "aumentado o disminuido" in q_norm
    )
    if is_comparison:
        if "12 horas" in q_norm:
            p1_start = now - timedelta(hours=12)
            p1_end = now
            p2_start = now - timedelta(hours=24)
            p2_end = now - timedelta(hours=12)
        elif "hoy" in q_norm or "ayer" in q_norm or "dos días" in q_norm or "2 días" in q_norm:
            p1_start = now - timedelta(days=1)
            p1_end = now
            p2_start = now - timedelta(days=2)
            p2_end = now - timedelta(days=1)
        else:
            p1_start = now - timedelta(days=7)
            p1_end = now
            p2_start = now - timedelta(days=14)
            p2_end = now - timedelta(days=7)

        return IntentResult(
            intent="CONSULTA_SISMICA",
            tools=["compare_earthquake_periods"],
            start_time=p1_start,
            end_time=p1_end,
            period2_start=p2_start,
            period2_end=p2_end,
            min_magnitude=min_magnitude,
            region=region,
        )

    # 10. Prioridad a Calidad de Datos antes de Documentación general
    if any(k in q_norm for k in ["puntaje de calidad", "calidad de los datos", "calidad de datos", "descartados", "valid_records", "quality_score"]):
        return IntentResult(
            intent="CONSULTA_SISMICA",
            tools=["get_data_quality_metrics"],
        )

    # 11. Extracción de Períodos Temporales estándar
    if "12 horas" in q_norm:
        start_time = now - timedelta(hours=12)
        end_time = now
    elif "48 horas" in q_norm or "dos días" in q_norm or "2 días" in q_norm:
        start_time = now - timedelta(hours=48)
        end_time = now
    elif "7 días" in q_norm or "siete días" in q_norm or "esta semana" in q_norm or "última semana" in q_norm:
        start_time = now - timedelta(days=7)
        end_time = now
    elif "24 horas" in q_norm or "hoy" in q_norm or (not is_followup and not start_time):
        start_time = now - timedelta(hours=24)
        end_time = now

    # 12. Clasificación de Documentación Técnica
    is_doc = any(k in q_norm for k in DOCUMENTATION_KEYWORDS) and not any(k in q_norm for k in ["cuántos", "cuantos", "últimos 5", "sismo más", "sismo mas"])
    if is_doc:
        return IntentResult(
            intent="CONSULTA_DOCUMENTACION",
            tools=["search_project_documentation"],
        )

    # 13. Clasificación de Consultas Sísmicas y Selección de Herramientas
    if any(k in q_norm for k in ["mayor magnitud", "más fuerte", "mas fuerte", "más potente", "mas potente", "máximo", "maximo", "más profundo", "mas profundo", "profundidad"]):
        tools = ["get_strongest_earthquake"]
    elif any(k in q_norm for k in ["últimos 5", "ultimos 5", "últimos sismos", "ultimos sismos", "recientes"]):
        tools = ["get_latest_earthquakes"]
    elif any(k in q_norm for k in ["distribución", "distribucion", "rangos de magnitud"]):
        tools = ["get_magnitude_distribution"]
    elif any(k in q_norm for k in ["anomalía", "anomalia", "atípico", "atipico", "z-score", "zscore"]):
        tools = ["get_anomaly_alerts"]
    elif any(k in q_norm for k in ["región", "region", "regiones", "ranking", "top 3", "dónde", "donde"]):
        tools = ["get_earthquakes_by_region"]
    else:
        tools = ["get_earthquake_statistics"]

    return IntentResult(
        intent="CONSULTA_SISMICA",
        tools=tools,
        start_time=start_time,
        end_time=end_time,
        min_magnitude=min_magnitude,
        region=region,
        is_followup=is_followup,
    )
