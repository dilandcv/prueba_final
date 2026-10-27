"""Herramientas analíticas deterministas sobre la capa Gold y Ops de PostgreSQL."""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_strongest_earthquake(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Retorna el evento sísmico de mayor magnitud en un intervalo o región."""
    query = """
        SELECT
            event_id,
            magnitude,
            place,
            region,
            time_utc,
            depth_km,
            latitude,
            longitude,
            tsunami_alert
        FROM gold.earthquakes
        WHERE (%s::timestamptz IS NULL OR time_utc >= %s)
          AND (%s::timestamptz IS NULL OR time_utc <= %s)
          AND (%s::varchar IS NULL OR region ILIKE %s)
        ORDER BY magnitude DESC, time_utc DESC
        LIMIT 1;
    """
    region_filter = f"%{region}%" if region else None
    cur.execute(query, (start_time, start_time, end_time, end_time, region_filter, region_filter))
    row = cur.fetchone()
    if not row:
        return {"found": False, "message": "No se encontraron sismos para el período o región especificada."}

    return {
        "found": True,
        "event_id": row[0],
        "magnitude": float(row[1]),
        "place": row[2] or "Ubicación no especificada",
        "region": row[3] or "Desconocida",
        "time_utc": row[4].strftime("%Y-%m-%d %H:%M:%S UTC") if row[4] else "N/D",
        "depth_km": float(row[5]) if row[5] is not None else None,
        "latitude": float(row[6]),
        "longitude": float(row[7]),
        "tsunami_alert": bool(row[8]),
    }


def get_earthquake_statistics(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Calcula agregaciones analíticas: conteo, promedio, máximo, tsunamis y profundidad."""
    query = """
        SELECT
            COUNT(*) AS total_events,
            ROUND(AVG(magnitude), 2) AS avg_magnitude,
            MAX(magnitude) AS max_magnitude,
            COUNT(*) FILTER (WHERE tsunami_alert = TRUE) AS tsunami_alerts_count,
            MAX(depth_km) AS max_depth_km
        FROM gold.earthquakes
        WHERE (%s::timestamptz IS NULL OR time_utc >= %s)
          AND (%s::timestamptz IS NULL OR time_utc <= %s)
          AND (%s::numeric IS NULL OR magnitude >= %s)
          AND (%s::varchar IS NULL OR region ILIKE %s);
    """
    region_filter = f"%{region}%" if region else None
    cur.execute(
        query,
        (
            start_time, start_time,
            end_time, end_time,
            min_magnitude, min_magnitude,
            region_filter, region_filter,
        ),
    )
    row = cur.fetchone()
    total = row[0] if row else 0
    return {
        "total_events": total,
        "avg_magnitude": float(row[1]) if row and row[1] is not None else 0.0,
        "max_magnitude": float(row[2]) if row and row[2] is not None else 0.0,
        "tsunami_alerts_count": row[3] if row else 0,
        "max_depth_km": float(row[4]) if row and row[4] is not None else None,
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else None,
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else None,
        "min_magnitude": min_magnitude,
        "region": region,
    }


def get_latest_earthquakes(
    cur,
    limit: int = 5,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Obtiene los últimos N eventos sísmicos registrados cronológicamente."""
    clamped_limit = max(1, min(limit, 50))
    query = """
        SELECT
            event_id,
            magnitude,
            place,
            region,
            time_utc,
            depth_km,
            tsunami_alert
        FROM gold.earthquakes
        WHERE (%s::numeric IS NULL OR magnitude >= %s)
          AND (%s::varchar IS NULL OR region ILIKE %s)
        ORDER BY time_utc DESC
        LIMIT %s;
    """
    region_filter = f"%{region}%" if region else None
    cur.execute(query, (min_magnitude, min_magnitude, region_filter, region_filter, clamped_limit))
    rows = cur.fetchall()
    return [
        {
            "event_id": r[0],
            "magnitude": float(r[1]),
            "place": r[2] or "Ubicación no especificada",
            "region": r[3] or "Desconocida",
            "time_utc": r[4].strftime("%Y-%m-%d %H:%M:%S UTC") if r[4] else "N/D",
            "depth_km": float(r[5]) if r[5] is not None else None,
            "tsunami_alert": bool(r[6]),
        }
        for r in rows
    ]


def get_earthquakes_by_region(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 5,
    region: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Calcula el ranking o conteo regional de actividad sísmica en un intervalo."""
    clamped_limit = max(1, min(limit, 20))
    query = """
        SELECT
            region,
            COUNT(*) AS total_events,
            MAX(magnitude) AS max_magnitude,
            ROUND(AVG(magnitude), 2) AS avg_magnitude
        FROM gold.earthquakes
        WHERE (%s::timestamptz IS NULL OR time_utc >= %s)
          AND (%s::timestamptz IS NULL OR time_utc <= %s)
          AND (%s::varchar IS NULL OR region ILIKE %s)
        GROUP BY region
        ORDER BY total_events DESC, max_magnitude DESC
        LIMIT %s;
    """
    region_filter = f"%{region}%" if region else None
    cur.execute(query, (start_time, start_time, end_time, end_time, region_filter, region_filter, clamped_limit))
    rows = cur.fetchall()
    return [
        {
            "region": r[0] or "Otras regiones",
            "total_events": int(r[1]),
            "max_magnitude": float(r[2]) if r[2] is not None else 0.0,
            "avg_magnitude": float(r[3]) if r[3] is not None else 0.0,
        }
        for r in rows
    ]


def get_magnitude_distribution(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Obtiene la distribución de eventos agrupados por intervalos de magnitud."""
    # Si no hay filtros de fecha, consultamos la tabla agregada gold.magnitude_distribution
    if not start_time and not end_time:
        cur.execute("SELECT magnitude_bracket, event_count FROM gold.magnitude_distribution ORDER BY event_count DESC;")
        return [{"magnitude_bracket": r[0], "event_count": int(r[1])} for r in cur.fetchall()]

    # Cálculo dinámico si hay rango temporal
    query = """
        SELECT
            CASE
                WHEN magnitude < 3.0 THEN '< 3.0'
                WHEN magnitude >= 3.0 AND magnitude < 4.0 THEN '3.0 - 3.9'
                WHEN magnitude >= 4.0 AND magnitude < 5.0 THEN '4.0 - 4.9'
                WHEN magnitude >= 5.0 AND magnitude < 6.0 THEN '5.0 - 5.9'
                ELSE '>= 6.0'
            END AS magnitude_bracket,
            COUNT(*) AS event_count
        FROM gold.earthquakes
        WHERE (%s::timestamptz IS NULL OR time_utc >= %s)
          AND (%s::timestamptz IS NULL OR time_utc <= %s)
        GROUP BY magnitude_bracket
        ORDER BY event_count DESC;
    """
    cur.execute(query, (start_time, start_time, end_time, end_time))
    return [{"magnitude_bracket": r[0], "event_count": int(r[1])} for r in cur.fetchall()]


def compare_earthquake_periods(
    cur,
    period1_start: datetime,
    period1_end: datetime,
    period2_start: datetime,
    period2_end: datetime,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Compara estadísticamente dos intervalos de tiempo para medir variación de actividad."""
    stats1 = get_earthquake_statistics(cur, start_time=period1_start, end_time=period1_end, min_magnitude=min_magnitude, region=region)
    stats2 = get_earthquake_statistics(cur, start_time=period2_start, end_time=period2_end, min_magnitude=min_magnitude, region=region)

    count1 = stats1["total_events"]
    count2 = stats2["total_events"]

    diff_events = count1 - count2
    percent_change = round(((count1 - count2) / count2) * 100.0, 1) if count2 > 0 else 0.0

    return {
        "period1": {
            "start": period1_start.strftime("%Y-%m-%d %H:%M"),
            "end": period1_end.strftime("%Y-%m-%d %H:%M"),
            "total_events": count1,
            "avg_magnitude": stats1["avg_magnitude"],
            "max_magnitude": stats1["max_magnitude"],
        },
        "period2": {
            "start": period2_start.strftime("%Y-%m-%d %H:%M"),
            "end": period2_end.strftime("%Y-%m-%d %H:%M"),
            "total_events": count2,
            "avg_magnitude": stats2["avg_magnitude"],
            "max_magnitude": stats2["max_magnitude"],
        },
        "comparison": {
            "delta_events": diff_events,
            "percent_change": percent_change,
            "trend": "aumento" if diff_events > 0 else ("disminución" if diff_events < 0 else "estable"),
        },
    }


def get_anomaly_alerts(cur, hours_lookback: int = 24, limit: int = 5) -> list[dict[str, Any]]:
    """Consulta las alertas estadísticas Z-Score registradas en ops.anomaly_alerts."""
    query = """
        SELECT
            region,
            hour_bucket,
            event_count,
            z_score,
            threshold,
            narrative_explanation
        FROM ops.anomaly_alerts
        WHERE hour_bucket >= NOW() - (%s || ' hours')::interval
        ORDER BY hour_bucket DESC, z_score DESC
        LIMIT %s;
    """
    cur.execute(query, (hours_lookback, limit))
    rows = cur.fetchall()
    return [
        {
            "region": r[0],
            "hour_bucket": r[1].strftime("%Y-%m-%d %H:%M UTC") if r[1] else "N/D",
            "event_count": int(r[2]),
            "z_score": float(r[3]),
            "threshold": float(r[4]),
            "narrative_explanation": r[5] or "Sin explicación",
        }
        for r in rows
    ]


def get_data_quality_metrics(cur) -> dict[str, Any]:
    """Obtiene el último reporte de calidad de datos en metrics.data_quality."""
    cur.execute(
        """
        SELECT quality_score, total_records, valid_records, invalid_records, failed_rules, evaluated_at
        FROM metrics.data_quality
        ORDER BY evaluated_at DESC
        LIMIT 1;
        """
    )
    row = cur.fetchone()
    if not row:
        return {
            "quality_score": 100.0,
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "failed_rules": {},
            "evaluated_at": None,
        }
    return {
        "quality_score": float(row[0]),
        "total_records": int(row[1]),
        "valid_records": int(row[2]),
        "invalid_records": int(row[3]),
        "failed_rules": row[4] if isinstance(row[4], dict) else {},
        "evaluated_at": row[5].strftime("%Y-%m-%d %H:%M:%S UTC") if row[5] else None,
    }
