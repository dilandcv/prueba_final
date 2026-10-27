"""Plantillas de prompts para IA local (Ollama) y fallbacks deterministas.

Garantiza respuestas consistentes y generación de reportes ejecutivos fidedignos
incluso ante la indisponibilidad total del modelo de lenguaje.
"""
from typing import Any, Optional


PROMPT_VERSION = "v1.0"

# Prompt estructurado para la explicación de anomalías por Z-Score
PROMPT_ANOMALY_V1 = """Eres un asistente analítico especializado en sismología observacional.
Se ha detectado una desviación estadística inusual en la frecuencia de sismos para la siguiente región:

- Región: {region}
- Intervalo horario: {hour_bucket} UTC
- Eventos registrados en la hora: {event_count}
- Media histórica reciente: {mean:.2f} sismos/hora
- Desviación estándar (σ): {stddev:.2f}
- Puntuación Z-Score calculada: {z_score:.2f} (Umbral de alerta: {threshold:.1f})
- Total de horas analizadas: {obs_count}

Instrucciones estrictas:
1. Redacta una explicación concisa (máximo 3 oraciones) describiendo la anomalía en términos de frecuencia observada.
2. Compara el conteo observado con el promedio histórico reciente.
3. ADVERTENCIA OBLIGATORIA: Indica explícitamente que este cálculo representa una anomalía estadística de frecuencia observada y NO es una predicción o pronóstico de futuros terremotos.
"""

# Prompt estructurado para el reporte narrativo ejecutivo diario
PROMPT_DAILY_SUMMARY_V1 = """Eres el analista principal de la Plataforma de Análisis Sísmico USGS.
A continuación se presentan las métricas analíticas consolidadas de las últimas 24 horas:

- Total de eventos registrados: {total_events}
- Sismo más potente: Magnitud {max_magnitude} en {max_place} a {max_depth} km de profundidad ({max_time} UTC)
- Magnitud promedio: {avg_magnitude}
- Alertas de tsunami emitidas: {tsunami_alerts_count}
- Regiones más activas: {top_regions_str}
- Distribución de magnitudes: {distribution_str}
- Tendencia temporal: {trend_str}

Instrucciones:
1. Redacta un informe ejecutivo estructurado en 3 párrafos:
   - Párrafo 1: Resumen de la actividad global y evento de mayor intensidad.
   - Párrafo 2: Zonas geográficas de mayor concentración y tendencia de las últimas 12 horas.
   - Párrafo 3: Estado de las alertas de tsunami y contexto operativo.
2. No inventes cifras. Utiliza exclusivamente las métricas provistas.
3. Menciona que los datos provienen de la capa Gold del USGS Medallion Pipeline.
"""


def format_anomaly_fallback(data: dict[str, Any]) -> str:
    """Genera una explicación determinista precisa cuando Ollama no está disponible.
    
    No predice sismos; documenta exclusivamente la desviación matemática observada.
    """
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

    # Formateo de lista de regiones
    regions_lines = []
    for r in top_regions[:5]:
        reg_name = r.get("region", "N/A")
        count = r.get("total_events_24h", 0)
        m_max = r.get("max_magnitude_24h")
        mag_str = f"M{m_max:.1f}" if m_max is not None else "N/D"
        regions_lines.append(f"  - **{reg_name}**: {count} sismos (magnitud máxima: {mag_str})")
    regions_text = "\n".join(regions_lines) if regions_lines else "  - Sin actividad regional destacada registrada."

    # Formateo de distribución
    dist_lines = []
    for d in distribution:
        bracket = d.get("magnitude_bracket", "N/A")
        c = d.get("event_count", 0)
        pct = (c / total_events * 100) if total_events > 0 else 0
        dist_lines.append(f"  - Rango {bracket}: {c} eventos ({pct:.1f}%)")
    dist_text = "\n".join(dist_lines) if dist_lines else "  - Distribución no disponible."

    # Tendencia horaria
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
