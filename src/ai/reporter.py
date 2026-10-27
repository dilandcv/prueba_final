"""Servicio de generación de reportes ejecutivos diarios de actividad sísmica.

Precalcula deterministamente todas las estadísticas, rankings, tendencias y
eventos destacados sobre la capa Gold para que el modelo de IA local (o el
fallback determinista) se limite exclusivamente a la redacción narrativa.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Optional

from src.ai.client import OllamaClient, record_ai_execution
from src.ai.prompts import (
    PROMPT_DAILY_SUMMARY_V1,
    PROMPT_VERSION,
    format_daily_report_fallback,
)
from src.common.db import get_db_connection


logger = logging.getLogger(__name__)


def calculate_daily_summary_metrics(cur: Any) -> dict[str, Any]:
    """Calcula previamente todas las métricas analíticas de las últimas 24 horas en Gold."""
    # 1. Total eventos, evento de máxima magnitud, promedio y alertas de tsunami
    cur.execute(
        """
        SELECT
            COUNT(*) AS total_events,
            COALESCE(AVG(magnitude), 0.0) AS avg_magnitude,
            COUNT(*) FILTER (WHERE tsunami_alert = TRUE) AS tsunami_alerts
        FROM gold.earthquakes
        WHERE time_utc >= CURRENT_TIMESTAMP - INTERVAL '24 hours';
        """
    )
    row_general = cur.fetchone() or (0, 0.0, 0)
    total_events = int(row_general[0])
    avg_mag = float(row_general[1])
    tsunami_alerts = int(row_general[2])

    # Evento de mayor intensidad en las 24h
    cur.execute(
        """
        SELECT
            magnitude,
            place,
            time_utc,
            depth_km
        FROM gold.earthquakes
        WHERE time_utc >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY magnitude DESC, time_utc DESC
        LIMIT 1;
        """
    )
    row_max = cur.fetchone()
    max_event = {
        "magnitude": float(row_max[0]) if row_max else None,
        "place": row_max[1] if row_max else "N/A",
        "time_utc": row_max[2].strftime("%Y-%m-%d %H:%M") if row_max and row_max[2] else "N/A",
        "depth_km": float(row_max[3]) if row_max and row_max[3] is not None else None,
    }

    # 2. Ranking de regiones más activas (Top 5)
    cur.execute(
        """
        SELECT
            region,
            total_events_24h,
            max_magnitude_24h
        FROM gold.regional_ranking
        ORDER BY total_events_24h DESC, max_magnitude_24h DESC
        LIMIT 5;
        """
    )
    rows_ranking = cur.fetchall()
    top_regions = [
        {
            "region": r[0],
            "total_events_24h": r[1],
            "max_magnitude_24h": float(r[2]) if r[2] is not None else None,
        }
        for r in rows_ranking
    ]

    # 3. Distribución por rangos de magnitud
    cur.execute(
        """
        SELECT
            magnitude_bracket,
            event_count
        FROM gold.magnitude_distribution
        ORDER BY magnitude_bracket ASC;
        """
    )
    rows_dist = cur.fetchall()
    distribution = [
        {"magnitude_bracket": r[0], "event_count": r[1]}
        for r in rows_dist
    ]

    # 4. Dinámica y tendencia temporal (primeras 12h vs últimas 12h del intervalo de 24h)
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE time_utc >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                  AND time_utc < CURRENT_TIMESTAMP - INTERVAL '12 hours'
            ) AS first_12h,
            COUNT(*) FILTER (
                WHERE time_utc >= CURRENT_TIMESTAMP - INTERVAL '12 hours'
            ) AS last_12h
        FROM gold.earthquakes
        WHERE time_utc >= CURRENT_TIMESTAMP - INTERVAL '24 hours';
        """
    )
    row_trend = cur.fetchone() or (0, 0)
    h1 = int(row_trend[0])
    h2 = int(row_trend[1])

    if h1 == 0 and h2 == 0:
        direction = "estable"
        pct_change = 0.0
    elif h1 == 0:
        direction = "creciente"
        pct_change = 100.0
    else:
        pct_change = ((h2 - h1) / h1) * 100.0
        if pct_change > 15.0:
            direction = "creciente"
        elif pct_change < -15.0:
            direction = "decreciente"
        else:
            direction = "estable"

    trend = {
        "first_12h_count": h1,
        "last_12h_count": h2,
        "direction": direction,
        "change_percent": round(pct_change, 1),
    }

    return {
        "total_events": total_events,
        "avg_magnitude": round(avg_mag, 2),
        "tsunami_alerts_count": tsunami_alerts,
        "max_event": max_event,
        "top_regions": top_regions,
        "magnitude_distribution": distribution,
        "trend": trend,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_daily_executive_report(airflow_run_id: Optional[str] = None) -> dict[str, Any]:
    """Genera el reporte ejecutivo diario: precalcula métricas en Gold y redacta con fallback."""
    logger.info("Iniciando generación de reporte diario ejecutivo...")

    # 1. Precalcular todas las cifras en Gold usando el rol ai_reader
    with get_db_connection(role="ai_reader") as conn:
        with conn.cursor() as cur:
            metrics = calculate_daily_summary_metrics(cur)

    # 2. Formatear variables para el prompt de IA
    max_ev = metrics["max_event"]
    top_regs_str = ", ".join(
        f"{r['region']} ({r['total_events_24h']} sismos)" for r in metrics["top_regions"]
    ) or "Sin actividad destacada"

    dist_str = ", ".join(
        f"{d['magnitude_bracket']}: {d['event_count']}" for d in metrics["magnitude_distribution"]
    ) or "Sin datos"

    trend_info = metrics["trend"]
    trend_str = (
        f"{trend_info['direction']} ({trend_info['first_12h_count']} sismos primeras 12h "
        f"vs {trend_info['last_12h_count']} sismos últimas 12h, cambio: {trend_info['change_percent']:+1f}%)"
    )

    prompt = PROMPT_DAILY_SUMMARY_V1.format(
        total_events=metrics["total_events"],
        max_magnitude=max_ev["magnitude"] if max_ev["magnitude"] is not None else "N/D",
        max_place=max_ev["place"],
        max_depth=max_ev["depth_km"] if max_ev["depth_km"] is not None else "N/D",
        max_time=max_ev["time_utc"],
        avg_magnitude=metrics["avg_magnitude"],
        tsunami_alerts_count=metrics["tsunami_alerts_count"],
        top_regions_str=top_regs_str,
        distribution_str=dist_str,
        trend_str=trend_str,
    )

    # 3. Invocar Ollama o fallback determinista
    client = OllamaClient()
    ai_result = client.generate(
        prompt=prompt,
        fallback_fn=format_daily_report_fallback,
        fallback_data=metrics,
    )

    # 4. Registrar auditoría de ejecución con rol pipeline
    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            execution_id = record_ai_execution(
                cur=cur,
                result=ai_result,
                automation_type="DAILY_REPORT",
                prompt_version=PROMPT_VERSION,
                airflow_run_id=airflow_run_id,
            )
            conn.commit()

    logger.info(
        "Reporte diario completado exitosamente (id: %d, fallback: %s, estado: %s)",
        execution_id,
        ai_result.used_fallback,
        ai_result.status,
    )

    return {
        "status": "SUCCESS",
        "execution_id": execution_id,
        "used_fallback": ai_result.used_fallback,
        "model_name": ai_result.model_name,
        "metrics": metrics,
        "report_text": ai_result.text,
    }
