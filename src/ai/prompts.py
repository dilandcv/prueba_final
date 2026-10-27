"""Gestor de prompts versionados, validación Pydantic y fallbacks deterministas.

Criterio de estimación de costo local:
La inferencia se ejecuta localmente mediante Ollama sobre hardware propio (CPU/GPU local),
por lo que no existe facturación de API de terceros. Por defecto, el costo por token es
0.0 (AI_COST_PER_TOKEN=0.0). Si la organización requiere computar costos de amortización
de infraestructura o consumo eléctrico, puede definirse una tarifa en AI_COST_PER_TOKEN
(ej. 0.000001 USD/token).
"""
import json
import logging
from pathlib import Path
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, Field, ValidationError


logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0"
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Aliases para compatibilidad con código existente
PROMPT_ANOMALY_V1 = """Eres un asistente analítico especializado en sismología observacional.
Región: {region}, Intervalo: {hour_bucket} UTC, Eventos: {event_count}, Media: {mean}, Stddev: {stddev}, Z-Score: {z_score}.
Responde en JSON con region, hour_bucket, event_count, z_score, explanation, is_observational_only (true), non_predictive_disclaimer."""

PROMPT_DAILY_SUMMARY_V1 = """Eres el analista principal de la Plataforma USGS.
Total eventos: {total_events}, Magnitud máx: {max_magnitude}, Promedio: {avg_magnitude}, Alertas tsunami: {tsunami_alerts_count}.
Responde en JSON con title, total_events, max_magnitude, avg_magnitude, tsunami_alerts_count, narrative_overview, regional_activity, tsunami_and_context, non_predictive_note."""

T = TypeVar("T", bound=BaseModel)


# ==============================================================================
# Modelos Pydantic para Validación Estructurada
# ==============================================================================
class AnomalyStructuredOutput(BaseModel):
    """Esquema de salida estructurada para explicaciones de anomalías Z-Score."""
    region: str = Field(..., description="Región geográfica analizada")
    hour_bucket: str = Field(..., description="Intervalo horario en formato UTC")
    event_count: int = Field(..., ge=0, description="Cantidad observada de eventos en la hora")
    z_score: float = Field(..., description="Puntaje Z-Score calculado")
    explanation: str = Field(..., min_length=15, description="Explicación narrativa de la frecuencia observada")
    is_observational_only: bool = Field(True, description="Bandera que confirma naturaleza puramente observacional")
    non_predictive_disclaimer: str = Field(..., min_length=15, description="Advertencia explícita de no predicción")

    def validate_consistency(self, authorized: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Verifica que el modelo no haya alterado ni alucinado las cifras precalculadas."""
        if self.event_count != authorized.get("event_count"):
            return False, f"Inconsistencia en event_count: modelo dio {self.event_count}, autorizado era {authorized.get('event_count')}"

        auth_zscore = float(authorized.get("z_score", 0.0))
        if abs(self.z_score - auth_zscore) > 0.05:
            return False, f"Inconsistencia en z_score: modelo dio {self.z_score}, autorizado era {auth_zscore}"

        # Verificar obligatoriedad de la advertencia de no-predicción
        combined_text = (self.explanation + " " + self.non_predictive_disclaimer).lower()
        if "predicci" in combined_text or "pronóstico" in combined_text or "pronostico" in combined_text:
            if not any(neg in combined_text for neg in ["no es", "no constituye", "no representa", "no predice"]):
                return False, "La respuesta sugiere falsamente capacidad predictiva de sismos"

        return True, None


class DailyReportStructuredOutput(BaseModel):
    """Esquema de salida estructurada para el informe ejecutivo diario."""
    title: str = Field(..., description="Título del informe")
    total_events: int = Field(..., ge=0, description="Total de sismos en las últimas 24h")
    max_magnitude: float = Field(..., ge=0.0, le=10.0, description="Magnitud máxima registrada")
    avg_magnitude: float = Field(..., ge=0.0, le=10.0, description="Magnitud promedio")
    tsunami_alerts_count: int = Field(..., ge=0, description="Alertas de tsunami emitidas")
    narrative_overview: str = Field(..., min_length=20, description="Resumen de actividad global")
    regional_activity: str = Field(..., min_length=20, description="Detalle regional y dinámica 12h")
    tsunami_and_context: str = Field(..., min_length=15, description="Contexto operativo y alertas de tsunami")
    non_predictive_note: str = Field(..., min_length=15, description="Nota técnica de mediciones históricas")

    def validate_consistency(self, authorized: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Verifica la coherencia matemática estricta con las métricas precalculadas."""
        auth_total = authorized.get("total_events", 0)
        if self.total_events != auth_total:
            return False, f"Inconsistencia en total_events: modelo dio {self.total_events}, autorizado era {auth_total}"

        auth_max_ev = authorized.get("max_event") or {}
        auth_max_mag = float(auth_max_ev.get("magnitude") or 0.0)
        if abs(self.max_magnitude - auth_max_mag) > 0.1:
            return False, f"Inconsistencia en max_magnitude: modelo dio {self.max_magnitude}, autorizado era {auth_max_mag}"

        auth_tsunami = authorized.get("tsunami_alerts_count", 0)
        if self.tsunami_alerts_count != auth_tsunami:
            return False, f"Inconsistencia en tsunami_alerts_count: modelo dio {self.tsunami_alerts_count}, autorizado era {auth_tsunami}"

        return True, None

    def to_markdown(self) -> str:
        """Convierte la salida estructurada validada a un reporte en formato Markdown."""
        return f"""# {self.title}
**Periodo analizado**: Últimas 24 horas (UTC) | **Fuente**: Capa Gold - USGS Medallion Platform
**Generación**: Validada mediante Pydantic (IA Local Ollama)

## 1. Panorama General de Actividad
{self.narrative_overview}
- **Total de eventos**: {self.total_events}
- **Magnitud máxima**: M{self.max_magnitude:.1f}
- **Magnitud promedio**: M{self.avg_magnitude:.2f}

## 2. Regiones y Dinámica Temporal
{self.regional_activity}

## 3. Estado de Alertas y Contexto Operativo
{self.tsunami_and_context}
- **Alertas de tsunami registradas**: {self.tsunami_alerts_count}

---
*{self.non_predictive_note}*
"""


# ==============================================================================
# Carga de Plantillas de Prompts Versionados
# ==============================================================================
def load_prompt_template(filename: str) -> str:
    """Carga un archivo de prompt desde el directorio prompts/ o lanza FileNotFound."""
    prompt_path = PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()

    # Fallback si se ejecuta en contenedor con montaje en /opt/airflow/prompts
    airflow_path = Path("/opt/airflow/prompts") / filename
    if airflow_path.exists():
        return airflow_path.read_text(encoding="utf-8").strip()

    raise FileNotFoundError(f"Archivo de prompt no encontrado: {filename} en {prompt_path}")


def get_anomaly_prompt_template() -> str:
    """Obtiene la plantilla de prompt para anomalías desde prompts/anomaly_v1.txt."""
    try:
        return load_prompt_template("anomaly_v1.txt")
    except Exception:
        # Plantilla segura de respaldo si no se encuentra el archivo
        return """Eres un asistente analítico especializado en sismología observacional.
Región: {region}, Intervalo: {hour_bucket} UTC, Eventos: {event_count}, Media: {mean}, Stddev: {stddev}, Z-Score: {z_score}.
Responde en JSON con region, hour_bucket, event_count, z_score, explanation, is_observational_only (true), non_predictive_disclaimer."""


def get_daily_summary_prompt_template() -> str:
    """Obtiene la plantilla de prompt para reporte diario desde prompts/daily_summary_v1.txt."""
    try:
        return load_prompt_template("daily_summary_v1.txt")
    except Exception:
        return """Eres el analista principal de la Plataforma USGS.
Total eventos: {total_events}, Magnitud máx: {max_magnitude}, Promedio: {avg_magnitude}, Alertas tsunami: {tsunami_alerts_count}.
Responde en JSON con title, total_events, max_magnitude, avg_magnitude, tsunami_alerts_count, narrative_overview, regional_activity, tsunami_and_context, non_predictive_note."""


# ==============================================================================
# Validación y Rechazo de Cifras No Autorizadas
# ==============================================================================
def parse_and_validate_json_response(
    raw_text: str,
    model_cls: Type[T],
    authorized_data: dict[str, Any],
) -> tuple[Optional[T], bool, Optional[str]]:
    """Extrae JSON, valida esquema con Pydantic y comprueba coherencia de cifras.
    
    Retorna (objeto_validado, es_valido, motivo_error).
    """
    if not raw_text or not raw_text.strip():
        return None, False, "Texto de respuesta vacío"

    # Extraer bloque JSON si viene envuelto en markdown ```json ... ```
    text = raw_text.strip()
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not json_match:
        return None, False, "No se encontró un bloque JSON válido en la respuesta"

    json_str = json_match.group(0)

    try:
        parsed_dict = json.loads(json_str)
    except json.JSONDecodeError as err:
        return None, False, f"JSON sintácticamente inválido: {err}"

    try:
        validated_obj = model_cls.model_validate(parsed_dict)
    except ValidationError as val_err:
        return None, False, f"Fallo de validación Pydantic: {val_err}"

    # Comprobación estricta de coherencia numérica
    if hasattr(validated_obj, "validate_consistency"):
        is_consistent, reason = validated_obj.validate_consistency(authorized_data)
        if not is_consistent:
            return None, False, f"Rechazo por inconsistencia de cifras: {reason}"

    return validated_obj, True, None


# ==============================================================================
# Fallbacks Deterministas Fidedignos
# ==============================================================================
def format_anomaly_fallback(data: dict[str, Any]) -> str:
    """Genera una explicación determinista precisa cuando Ollama no está disponible o es rechazado."""
    region = data.get("region", "Desconocida")
    hour_bucket = data.get("hour_bucket", "N/A")
    event_count = data.get("event_count", 0)
    mean = float(data.get("mean", 0.0))
    stddev = float(data.get("stddev", 0.0))
    z_score = float(data.get("z_score", 0.0))
    threshold = float(data.get("threshold", 3.0))

    return (
        f"Alerta estadística de frecuencia sísmica (Z-Score: {z_score:.2f}, umbral: {threshold:.1f}). "
        f"En la región de '{region}' se registraron {event_count} eventos en el intervalo {hour_bucket} UTC, "
        f"frente a un promedio histórico reciente de {mean:.2f} eventos/hora (desviación estándar σ={stddev:.2f}). "
        f"Esta métrica describe una acumulación observada de eventos atípica respecto a la ventana analizada; "
        f"no constituye en ningún caso una predicción ni pronóstico de actividad sísmica futura."
    )


def format_daily_report_fallback(metrics: dict[str, Any]) -> str:
    """Genera el reporte ejecutivo diario estructurado de forma 100% determinista."""
    total_events = metrics.get("total_events", 0)
    max_ev = metrics.get("max_event") or {}
    max_mag = max_ev.get("magnitude", "N/D")
    max_place = max_ev.get("place", "Ubicación no disponible")
    max_depth = max_ev.get("depth_km", "N/D")
    max_time = max_ev.get("time_utc", "N/D")
    avg_mag = metrics.get("avg_magnitude", 0.0)
    tsunami_alerts = metrics.get("tsunami_alerts_count", 0)
    top_regions = metrics.get("top_regions", [])
    distribution = metrics.get("magnitude_distribution", [])
    trend = metrics.get("trend", {})

    regions_lines = []
    for r in top_regions[:5]:
        reg_name = r.get("region", "N/A")
        count = r.get("total_events_24h", 0)
        m_max = r.get("max_magnitude_24h")
        mag_str = f"M{m_max:.1f}" if m_max is not None else "N/D"
        regions_lines.append(f"  - **{reg_name}**: {count} sismos (magnitud máxima: {mag_str})")
    regions_text = "\n".join(regions_lines) if regions_lines else "  - Sin actividad regional destacada registrada."

    dist_lines = []
    for d in distribution:
        bracket = d.get("magnitude_bracket", "N/A")
        c = d.get("event_count", 0)
        pct = (c / total_events * 100) if total_events > 0 else 0
        dist_lines.append(f"  - Rango {bracket}: {c} eventos ({pct:.1f}%)")
    dist_text = "\n".join(dist_lines) if dist_lines else "  - Distribución no disponible."

    h1_count = trend.get("first_12h_count", 0)
    h2_count = trend.get("last_12h_count", 0)
    trend_desc = trend.get("direction", "estable")
    trend_pct = trend.get("change_percent", 0.0)

    return f"""# Resumen Ejecutivo Diario de Actividad Sísmica
**Periodo analizado**: Últimas 24 horas (UTC) | **Fuente**: Capa Gold - USGS Medallion Platform
**Modo de generación**: Fallback determinista validado

## 1. Panorama General de Actividad
Durante las últimas 24 horas se procesaron y consolidaron **{total_events} eventos sísmicos** con magnitud igual o superior a 2.5 en la capa analítica Gold.
- **Magnitud promedio observada**: {avg_mag:.2f}
- **Evento de mayor intensidad**: Magnitud **{max_mag}** localizado en *{max_place}*, a una profundidad de {max_depth} km ({max_time} UTC).
- **Alertas de tsunami registradas**: **{tsunami_alerts}** eventos con bandera de alerta emitida por centros de alerta de tsunamis.

## 2. Regiones con Mayor Concentración Sísmica
Las 5 zonas de mayor concentración de actividad en el periodo son:
{regions_text}

## 3. Dinámica Temporal y Tendencia
Comparando la actividad entre la primera mitad del periodo (primeras 12 horas: {h1_count} sismos) y la segunda mitad (últimas 12 horas: {h2_count} sismos), se observa una **tendencia {trend_desc}** (variación del {trend_pct:+.1f}%).

## 4. Distribución por Rango de Magnitud
{dist_text}

---
*Nota técnica: Este informe ha sido compilado a partir de agregaciones analíticas deterministas calculadas mediante SQL sobre la capa Gold. Las métricas reflejan mediciones instrumentales históricas y no constituyen predicciones geofísicas.*
"""
