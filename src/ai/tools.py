"""Herramientas analíticas tipadas para el agente de IA sobre la capa Gold y Ops."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.ai.rag import search_project_documentation as rag_search


def get_strongest_earthquake(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Obtiene el evento sísmico de mayor magnitud registrado en un período o región."""
    where_clauses = []
    params: list[Any] = []

    if start_time:
        where_clauses.append("time_utc >= %s")
        params.append(start_time)
    if end_time:
        where_clauses.append("time_utc <= %s")
        params.append(end_time)
    if region:
        where_clauses.append("region ILIKE %s")
        params.append(f"%{region}%")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"""
        SELECT event_id, magnitude, place, region, time_utc, depth_km, latitude, longitude, tsunami_alert
        FROM gold.earthquakes
        {where_str}
        ORDER BY magnitude DESC NULLS LAST
        LIMIT 1;
    """
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        return {"found": False, "message": "No se encontraron eventos sísmicos en el rango solicitado."}

    return {
        "found": True,
        "event_id": row[0],
        "magnitude": float(row[1]) if row[1] is not None else None,
        "place": row[2] or "Ubicación desconocida",
        "region": row[3] or "Sin región",
        "time_utc": row[4].isoformat() if row[4] else None,
        "depth_km": float(row[5]) if row[5] is not None else None,
        "latitude": float(row[6]) if row[6] is not None else None,
        "longitude": float(row[7]) if row[7] is not None else None,
        "tsunami_alert": bool(row[8]),
    }


def get_earthquake_statistics(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Calcula estadísticas agregadas (total eventos, promedio, máximo, alertas tsunami)."""
    where_clauses = []
    params: list[Any] = []

    if start_time:
        where_clauses.append("time_utc >= %s")
        params.append(start_time)
    if end_time:
        where_clauses.append("time_utc <= %s")
        params.append(end_time)
    if min_magnitude is not None:
        where_clauses.append("magnitude >= %s")
        params.append(min_magnitude)
    if region:
        where_clauses.append("region ILIKE %s")
        params.append(f"%{region}%")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"""
        SELECT
            COUNT(*) AS total_events,
            ROUND(AVG(magnitude), 2) AS avg_magnitude,
            MAX(magnitude) AS max_magnitude,
            COUNT(*) FILTER (WHERE tsunami_alert = TRUE) AS tsunami_alerts_count,
            MIN(time_utc) AS min_time,
            MAX(time_utc) AS max_time
        FROM gold.earthquakes
        {where_str};
    """
    cur.execute(sql, tuple(params))
    row = cur.fetchone()

    total = row[0] if row else 0
    return {
        "total_events": total,
        "avg_magnitude": float(row[1]) if row and row[1] is not None else 0.0,
        "max_magnitude": float(row[2]) if row and row[2] is not None else 0.0,
        "tsunami_alerts_count": row[3] if row else 0,
        "min_time": row[4].isoformat() if row and row[4] else None,
        "max_time": row[5].isoformat() if row and row[5] else None,
        "filter_applied": {
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "min_magnitude": min_magnitude,
            "region": region,
        },
    }


def get_latest_earthquakes(
    cur,
    limit: int = 5,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Obtiene los últimos N eventos sísmicos registrados."""
    where_clauses = []
    params: list[Any] = []

    if min_magnitude is not None:
        where_clauses.append("magnitude >= %s")
        params.append(min_magnitude)
    if region:
        where_clauses.append("region ILIKE %s")
        params.append(f"%{region}%")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    limit_val = max(1, min(limit, 20))
    params.append(limit_val)

    sql = f"""
        SELECT event_id, magnitude, place, region, time_utc, depth_km, tsunami_alert
        FROM gold.earthquakes
        {where_str}
        ORDER BY time_utc DESC
        LIMIT %s;
    """
    cur.execute(sql, tuple(params))
    events = []
    for r in cur.fetchall():
        events.append({
            "event_id": r[0],
            "magnitude": float(r[1]) if r[1] is not None else 0.0,
            "place": r[2] or "Ubicación desconocida",
            "region": r[3] or "Sin región",
            "time_utc": r[4].isoformat() if r[4] else None,
            "depth_km": float(r[5]) if r[5] is not None else 0.0,
            "tsunami_alert": bool(r[6]),
        })
    return events


def get_earthquakes_by_region(
    cur,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    region: Optional[str] = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Devuelve el ranking regional o las estadísticas de una región específica."""
    limit_val = max(1, min(limit, 20))

    if region:
        # Consulta para una región específica
        stats = get_earthquake_statistics(cur, start_time=start_time, end_time=end_time, region=region)
        return [{
            "region": region,
            "total_events": stats["total_events"],
            "avg_magnitude": stats["avg_magnitude"],
            "max_magnitude": stats["max_magnitude"],
        }]

    # Ranking agregado
    where_clauses = []
    params: list[Any] = []
    if start_time:
        where_clauses.append("time_utc >= %s")
        params.append(start_time)
    if end_time:
        where_clauses.append("time_utc <= %s")
        params.append(end_time)

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    params.append(limit_val)

    sql = f"""
        SELECT
            region,
            COUNT(*) AS total_events,
            ROUND(AVG(magnitude), 2) AS avg_magnitude,
            MAX(magnitude) AS max_magnitude
        FROM gold.earthquakes
        {where_str}
        GROUP BY region
        ORDER BY total_events DESC, max_magnitude DESC
        LIMIT %s;
    """
    cur.execute(sql, tuple(params))
    rows = []
    for r in cur.fetchall():
        rows.append({
            "region": r[0] or "Otras regiones",
            "total_events": r[1],
            "avg_magnitude": float(r[2]) if r[2] is not None else 0.0,
            "max_magnitude": float(r[3]) if r[3] is not None else 0.0,
        })
    return rows


def compare_earthquake_periods(
    cur,
    period1_start: datetime,
    period1_end: datetime,
    period2_start: datetime,
    period2_end: datetime,
    min_magnitude: Optional[float] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Compara dos ventanas de tiempo (ej. esta semana vs semana anterior)."""
    p1 = get_earthquake_statistics(cur, start_time=period1_start, end_time=period1_end, min_magnitude=min_magnitude, region=region)
    p2 = get_earthquake_statistics(cur, start_time=period2_start, end_time=period2_end, min_magnitude=min_magnitude, region=region)

    delta_events = p1["total_events"] - p2["total_events"]
    delta_avg = round(p1["avg_magnitude"] - p2["avg_magnitude"], 2)

    direction = "aumento" if delta_events > 0 else ("disminución" if delta_events < 0 else "estable")
    percent_change = (
        round((delta_events / p2["total_events"]) * 100.0, 1)
        if p2["total_events"] > 0
        else 0.0
    )

    return {
        "period1": {
            "start": period1_start.isoformat(),
            "end": period1_end.isoformat(),
            "total_events": p1["total_events"],
            "avg_magnitude": p1["avg_magnitude"],
            "max_magnitude": p1["max_magnitude"],
        },
        "period2": {
            "start": period2_start.isoformat(),
            "end": period2_end.isoformat(),
            "total_events": p2["total_events"],
            "avg_magnitude": p2["avg_magnitude"],
            "max_magnitude": p2["max_magnitude"],
        },
        "comparison": {
            "delta_events": delta_events,
            "delta_avg_magnitude": delta_avg,
            "direction": direction,
            "percent_change": percent_change,
        },
    }


def get_magnitude_distribution(cur) -> list[dict[str, Any]]:
    """Devuelve la distribución de sismos por rangos de magnitud."""
    cur.execute("SELECT magnitude_bracket, event_count FROM gold.magnitude_distribution ORDER BY event_count DESC;")
    return [{"magnitude_bracket": r[0], "event_count": r[1]} for r in cur.fetchall()]


def get_anomaly_alerts(cur, hours_lookback: int = 24, limit: int = 5) -> list[dict[str, Any]]:
    """Obtiene alertas de anomalías estadísticas Z-Score recientes."""
    limit_val = max(1, min(limit, 20))
    since = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    cur.execute(
        """
        SELECT region, hour_bucket, event_count, z_score, threshold, narrative_explanation
        FROM ops.anomaly_alerts
        WHERE detected_at >= %s
        ORDER BY detected_at DESC
        LIMIT %s;
        """,
        (since, limit_val),
    )
    alerts = []
    for r in cur.fetchall():
        alerts.append({
            "region": r[0],
            "hour_bucket": r[1].isoformat() if r[1] else None,
            "event_count": r[2],
            "z_score": float(r[3]),
            "threshold": float(r[4]),
            "narrative_explanation": r[5],
        })
    return alerts


def get_data_quality_metrics(cur) -> dict[str, Any]:
    """Obtiene el último resumen de calidad de datos evaluado."""
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
        "total_records": row[1],
        "valid_records": row[2],
        "invalid_records": row[3],
        "failed_rules": row[4] if isinstance(row[4], dict) else {},
        "evaluated_at": row[5].isoformat() if row[5] else None,
    }
