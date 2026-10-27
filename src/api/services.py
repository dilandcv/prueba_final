"""Servicios de acceso a datos para la API REST.

REGLAS ARQUITECTÓNICAS:
- Consulta únicamente Gold y tablas operativas autorizadas.
- Utiliza estrictamente el rol 'api_reader' (solo lectura).
- Consultas SQL parametrizadas para prevenir inyección SQL.
- No utiliza pandas, Polars ni Dask.
"""
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Optional

from src.api.schemas import (
    AIReportItem,
    AnomalyAlertItem,
    GeneralIndicatorsResponse,
    HealthResponse,
    MagnitudeDistributionItem,
    MapEventItem,
    PipelineStatusResponse,
    QualitySummaryResponse,
    RegionalRankingItem,
    TimeSeriesPoint,
)
from src.common.db import get_db_connection


logger = logging.getLogger(__name__)


class AnalyticsService:
    """Servicio de consultas analíticas sobre esquemas Gold y Ops."""

    @staticmethod
    def check_health() -> HealthResponse:
        """Verifica conectividad contra PostgreSQL usando api_reader."""
        try:
            with get_db_connection(role="api_reader") as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            return HealthResponse(
                status="UP",
                database="CONNECTED",
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.error("Fallo de salud en base de datos: %s", e)
            return HealthResponse(
                status="DEGRADED",
                database="DISCONNECTED",
                timestamp=datetime.now(timezone.utc),
            )

    @staticmethod
    def get_general_indicators(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_magnitude: Optional[float] = None,
        region: Optional[str] = None,
    ) -> GeneralIndicatorsResponse:
        """Calcula indicadores consolidados de sismos, alertas y calidad."""
        conditions = []
        params = []

        if start_date:
            conditions.append("time_utc >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("time_utc <= %s")
            params.append(end_date)
        if min_magnitude is not None:
            conditions.append("magnitude >= %s")
            params.append(min_magnitude)
        if region:
            conditions.append("region = %s")
            params.append(region)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                # 1. Consulta agregada sobre gold.earthquakes
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        MAX(magnitude),
                        AVG(magnitude),
                        COALESCE(SUM(CASE WHEN tsunami_alert THEN 1 ELSE 0 END), 0)
                    FROM gold.earthquakes
                    {where_clause};
                    """,
                    params,
                )
                row = cur.fetchone()
                count = row[0] if row else 0
                max_mag = float(row[1]) if row and row[1] is not None else None
                avg_mag = round(float(row[2]), 2) if row and row[2] is not None else None
                tsunami_count = int(row[3]) if row and row[3] is not None else 0

                # 2. Último puntaje de calidad registrado
                cur.execute(
                    """
                    SELECT quality_score
                    FROM metrics.data_quality
                    ORDER BY evaluated_at DESC
                    LIMIT 1;
                    """
                )
                q_row = cur.fetchone()
                quality_score = float(q_row[0]) if q_row else 100.0

                # 3. Fecha de última disponibilidad
                cur.execute(
                    """
                    SELECT available_at
                    FROM ops.data_availability
                    WHERE status = 'AVAILABLE'
                    ORDER BY id DESC
                    LIMIT 1;
                    """
                )
                a_row = cur.fetchone()
                last_update = a_row[0] if a_row else None

        return GeneralIndicatorsResponse(
            events_count=count,
            max_magnitude=max_mag,
            avg_magnitude=avg_mag,
            tsunami_alerts_count=tsunami_count,
            quality_score=quality_score,
            last_update=last_update,
        )

    @staticmethod
    def get_timeseries(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_magnitude: Optional[float] = None,
        region: Optional[str] = None,
    ) -> list[TimeSeriesPoint]:
        """Obtiene la serie temporal de eventos agrupados por hora UTC."""
        conditions = []
        params = []

        if start_date:
            conditions.append("time_utc >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("time_utc <= %s")
            params.append(end_date)
        if min_magnitude is not None:
            conditions.append("magnitude >= %s")
            params.append(min_magnitude)
        if region:
            conditions.append("region = %s")
            params.append(region)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        DATE_TRUNC('hour', time_utc) AS hour_bucket,
                        COUNT(*) AS total_events,
                        ROUND(AVG(magnitude), 2) AS avg_magnitude,
                        MAX(magnitude) AS max_magnitude
                    FROM gold.earthquakes
                    {where_clause}
                    GROUP BY DATE_TRUNC('hour', time_utc)
                    ORDER BY hour_bucket ASC;
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [
            TimeSeriesPoint(
                hour_bucket=r[0],
                total_events=r[1],
                avg_magnitude=float(r[2]) if r[2] is not None else None,
                max_magnitude=float(r[3]) if r[3] is not None else None,
            )
            for r in rows
        ]

    @staticmethod
    def get_magnitude_distribution(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        region: Optional[str] = None,
    ) -> list[MagnitudeDistributionItem]:
        """Obtiene el desglose de sismos por rangos de magnitud."""
        conditions = []
        params = []

        if start_date:
            conditions.append("time_utc >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("time_utc <= %s")
            params.append(end_date)
        if region:
            conditions.append("region = %s")
            params.append(region)

        # Si no hay filtros ad-hoc, se lee directamente la tabla agregada en Gold
        if not conditions:
            with get_db_connection(role="api_reader") as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT magnitude_bracket, event_count
                        FROM gold.magnitude_distribution
                        ORDER BY event_count DESC;
                        """
                    )
                    rows = cur.fetchall()
            return [
                MagnitudeDistributionItem(magnitude_bracket=r[0], event_count=r[1])
                for r in rows
            ]

        # Si hay filtros aplicados, se calcula dinámicamente con los corchetes estándar
        where_clause = f"WHERE {' AND '.join(conditions)}"
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        CASE
                            WHEN magnitude < 3.0 THEN '2.5 - 2.9'
                            WHEN magnitude < 4.0 THEN '3.0 - 3.9'
                            WHEN magnitude < 5.0 THEN '4.0 - 4.9'
                            WHEN magnitude < 6.0 THEN '5.0 - 5.9'
                            ELSE '6.0+'
                        END AS magnitude_bracket,
                        COUNT(*) AS event_count
                    FROM gold.earthquakes
                    {where_clause}
                    GROUP BY magnitude_bracket
                    ORDER BY event_count DESC;
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [
            MagnitudeDistributionItem(magnitude_bracket=r[0], event_count=r[1])
            for r in rows
        ]

    @staticmethod
    def get_regional_ranking(limit: int = 10) -> list[RegionalRankingItem]:
        """Retorna las regiones con mayor actividad sísmica en las últimas 24 horas."""
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        region,
                        total_events_24h,
                        max_magnitude_24h,
                        ROW_NUMBER() OVER (ORDER BY total_events_24h DESC, max_magnitude_24h DESC) AS rank_position
                    FROM gold.regional_ranking
                    ORDER BY rank_position ASC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            RegionalRankingItem(
                region=r[0],
                total_events_24h=r[1],
                max_magnitude_24h=float(r[2]) if r[2] is not None else None,
                rank_position=r[3],
            )
            for r in rows
        ]

    @staticmethod
    def get_map_events(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_magnitude: Optional[float] = None,
        region: Optional[str] = None,
        limit: int = 500,
    ) -> list[MapEventItem]:
        """Retorna eventos sísmicos con coordenadas para renderizado en mapa Leaflet."""
        conditions = []
        params = []

        if start_date:
            conditions.append("time_utc >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("time_utc <= %s")
            params.append(end_date)
        if min_magnitude is not None:
            conditions.append("magnitude >= %s")
            params.append(min_magnitude)
        if region:
            conditions.append("region = %s")
            params.append(region)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        event_id,
                        magnitude,
                        place,
                        region,
                        time_utc,
                        latitude,
                        longitude,
                        depth_km,
                        tsunami_alert
                    FROM gold.earthquakes
                    {where_clause}
                    ORDER BY time_utc DESC
                    LIMIT %s;
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [
            MapEventItem(
                event_id=r[0],
                magnitude=float(r[1]),
                place=r[2],
                region=r[3],
                time_utc=r[4],
                latitude=float(r[5]),
                longitude=float(r[6]),
                depth_km=float(r[7]) if r[7] is not None else None,
                tsunami_alert=bool(r[8]),
            )
            for r in rows
        ]

    @staticmethod
    def get_quality_summary() -> QualitySummaryResponse:
        """Obtiene el último resumen de calidad registrado en metrics.data_quality."""
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        quality_score,
                        total_records,
                        valid_records,
                        invalid_records,
                        failed_rules,
                        evaluated_at
                    FROM metrics.data_quality
                    ORDER BY evaluated_at DESC
                    LIMIT 1;
                    """
                )
                row = cur.fetchone()

        if not row:
            return QualitySummaryResponse(
                quality_score=100.0,
                total_records=0,
                valid_records=0,
                invalid_records=0,
                failed_rules={},
                evaluated_at=None,
            )

        return QualitySummaryResponse(
            quality_score=float(row[0]),
            total_records=row[1],
            valid_records=row[2],
            invalid_records=row[3],
            failed_rules=row[4] if isinstance(row[4], dict) else {},
            evaluated_at=row[5],
        )

    @staticmethod
    def get_anomaly_alerts(limit: int = 20) -> list[AnomalyAlertItem]:
        """Obtiene alertas operativas de anomalías registradas."""
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        detected_at,
                        region,
                        hour_bucket,
                        event_count,
                        z_score,
                        threshold,
                        narrative_explanation
                    FROM ops.anomaly_alerts
                    ORDER BY detected_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            AnomalyAlertItem(
                id=r[0],
                detected_at=r[1],
                region=r[2],
                hour_bucket=r[3],
                event_count=r[4],
                z_score=float(r[5]),
                threshold=float(r[6]),
                narrative_explanation=r[7],
            )
            for r in rows
        ]

    @staticmethod
    def get_ai_reports(limit: int = 10) -> list[AIReportItem]:
        """Obtiene el historial de ejecuciones y reportes generados por el módulo de IA."""
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        executed_at,
                        automation_type,
                        model_name,
                        status,
                        used_fallback
                    FROM ops.ai_executions
                    ORDER BY executed_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            AIReportItem(
                id=r[0],
                executed_at=r[1],
                automation_type=r[2],
                model_name=r[3],
                status=r[4],
                used_fallback=bool(r[5]),
            )
            for r in rows
        ]

    @staticmethod
    def get_pipeline_status() -> PipelineStatusResponse:
        """Obtiene el estado de la última corrida de Airflow y disponibilidad de datos."""
        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                # Última ejecución
                cur.execute(
                    """
                    SELECT status, batch_id
                    FROM ops.pipeline_executions
                    ORDER BY id DESC
                    LIMIT 1;
                    """
                )
                exec_row = cur.fetchone()
                last_run_status = exec_row[0] if exec_row else "UNKNOWN"
                last_batch_id = str(exec_row[1]) if exec_row else None

                # Última disponibilidad
                cur.execute(
                    """
                    SELECT batch_id, available_at, records_processed, status
                    FROM ops.data_availability
                    WHERE status = 'AVAILABLE'
                    ORDER BY id DESC
                    LIMIT 1;
                    """
                )
                avail_row = cur.fetchone()

        if avail_row:
            avail_batch = str(avail_row[0])
            available_at = avail_row[1]
            records_proc = avail_row[2]
            overall_status = "HEALTHY" if last_run_status in ("SUCCESS", "UNKNOWN") else "DEGRADED"
        else:
            avail_batch = last_batch_id
            available_at = None
            records_proc = 0
            overall_status = "HEALTHY"

        return PipelineStatusResponse(
            status=overall_status,
            last_run_status=last_run_status,
            last_batch_id=avail_batch,
            last_available_at=available_at,
            records_processed=records_proc,
        )

    @staticmethod
    def get_latest_availability(after_id: Optional[int] = None) -> Optional[dict[str, Any]]:
        """Comprueba si hay un nuevo lote marcado como AVAILABLE para notificaciones SSE."""
        query = """
            SELECT id, batch_id, available_at, records_processed, status
            FROM ops.data_availability
            WHERE status = 'AVAILABLE'
        """
        params = []
        if after_id is not None:
            query += " AND id > %s"
            params.append(after_id)

        query += " ORDER BY id DESC LIMIT 1;"

        with get_db_connection(role="api_reader") as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()

        if row:
            return {
                "id": row[0],
                "batch_id": str(row[1]),
                "available_at": row[2].isoformat(),
                "records_processed": row[3],
                "status": row[4],
            }
        return None
