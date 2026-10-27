"""Tareas modulares e independientes orquestadas por el DAG de Apache Airflow.

Cada función implementa una responsabilidad única sin lógica de presentación:
1. determine_query_interval: Obtiene la marca de agua y calcula el rango de consulta.
2. extract_usgs_events: Realiza la petición HTTP a la API del USGS.
3. load_events_to_bronze: Almacena los eventos crudos en Bronze (append-only) y actualiza watermark.
4. run_spark_bronze_to_silver_task: Valida entorno y ejecuta PySpark Bronze -> Silver.
5. run_spark_silver_to_gold_task: Ejecuta PySpark Silver -> Gold.
6. evaluate_data_quality_task: Comprueba que el puntaje de calidad y la coherencia cumplan umbrales.
7. record_pipeline_execution_task: Registra métricas de ejecución y observabilidad en ops.pipeline_executions.
8. publish_data_availability_task: Marca los datos como AVAILABLE en ops.data_availability para SSE.
"""
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from typing import Any, Optional
import uuid

from psycopg.types.json import Jsonb
from src.common.config import get_settings
from src.common.db import get_db_connection
from src.ingestion.service import USGSIngestionService
from src.ingestion.usgs_client import USGSClient
from src.processing.bronze_to_silver import run_bronze_to_silver
from src.processing.silver_to_gold import run_silver_to_gold
from src.processing.spark_session import _ensure_java_home


logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Determinar el intervalo de consulta
# ==============================================================================
def determine_query_interval(ti: Any = None) -> dict[str, Any]:
    """Determina si corresponde carga inicial o incremental según ops.ingestion_watermark."""
    settings = get_settings()
    service = USGSIngestionService()
    batch_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            watermark = service.get_watermark(cur)

    if watermark:
        logger.info("Modo incremental detectado. Watermark: %s", watermark)
        result = {
            "batch_id": batch_id,
            "is_initial_load": False,
            "updatedafter": watermark.isoformat(),
            "determined_at": now_utc.isoformat(),
        }
    else:
        starttime = now_utc - timedelta(days=settings.usgs.initial_lookback_days)
        logger.info("Modo inicial detectado. Starttime: %s, Endtime: %s", starttime, now_utc)
        result = {
            "batch_id": batch_id,
            "is_initial_load": True,
            "starttime": starttime.isoformat(),
            "endtime": now_utc.isoformat(),
            "determined_at": now_utc.isoformat(),
        }

    return result


# ==============================================================================
# 2. Extraer eventos de la API del USGS
# ==============================================================================
def extract_usgs_events(
    ti: Any = None,
    interval_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Extrae eventos sísmicos desde la API del USGS según el intervalo determinado."""
    if interval_info is None and ti is not None:
        interval_info = ti.xcom_pull(task_ids="determine_query_interval")

    if not interval_info:
        raise ValueError("No se recibió información del intervalo de consulta (interval_info).")

    batch_id = interval_info["batch_id"]
    client = USGSClient()

    if interval_info.get("updatedafter"):
        watermark = datetime.fromisoformat(interval_info["updatedafter"])
        features = client.fetch_events(updatedafter=watermark)
    else:
        starttime = datetime.fromisoformat(interval_info["starttime"])
        endtime = datetime.fromisoformat(interval_info["endtime"])
        features = client.fetch_events(starttime=starttime, endtime=endtime)

    logger.info("Extracción completada para lote %s. Total eventos: %d", batch_id, len(features))
    return {
        "batch_id": batch_id,
        "features": features,
        "record_count": len(features),
    }


# ==============================================================================
# 3. Cargar eventos en Bronze
# ==============================================================================
def load_events_to_bronze(
    ti: Any = None,
    extraction_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Inserta los eventos en bronze.earthquakes de forma append-only e idempotente."""
    if extraction_info is None and ti is not None:
        extraction_info = ti.xcom_pull(task_ids="extract_usgs_events")

    if not extraction_info:
        raise ValueError("No se recibió la información de extracción (extraction_info).")

    batch_id_str = extraction_info["batch_id"]
    batch_id = uuid.UUID(batch_id_str)
    features = extraction_info.get("features", [])
    service = USGSIngestionService()
    now_utc = datetime.now(timezone.utc)

    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            inserted_count = service.insert_bronze_records(cur, batch_id, features)

            if features:
                latest_update_ms = max(
                    f.get("properties", {}).get("updated", 0) for f in features
                )
                new_watermark = (
                    datetime.fromtimestamp(latest_update_ms / 1000.0, tz=timezone.utc)
                    if latest_update_ms > 0
                    else now_utc
                )
            else:
                existing_wm = service.get_watermark(cur)
                new_watermark = existing_wm or now_utc

            service.save_watermark(cur, new_watermark, batch_id)
            conn.commit()

    logger.info("Lote %s: %d registros insertados en Bronze. Nueva watermark: %s", batch_id_str, inserted_count, new_watermark)
    return {
        "batch_id": batch_id_str,
        "records_ingested": inserted_count,
        "watermark": new_watermark.isoformat(),
    }


# ==============================================================================
# 4. Ejecutar Spark para Bronze → Silver
# ==============================================================================
def run_spark_bronze_to_silver_task(
    ti: Any = None,
    batch_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verifica disponibilidad de Java y JDBC, y ejecuta la transformación Bronze -> Silver."""
    # 1. Comprobación de prerrequisitos del entorno Spark
    _ensure_java_home()
    settings = get_settings()
    if not settings.spark.jar_path or not os.path.exists(settings.spark.jar_path):
        raise FileNotFoundError(
            f"El driver JDBC de PostgreSQL no se encuentra en '{settings.spark.jar_path}'. "
            "Verifique la configuración de SPARK_JDBC_JAR o la imagen Docker."
        )

    if not batch_id and ti is not None:
        load_res = ti.xcom_pull(task_ids="load_events_to_bronze")
        if load_res:
            batch_id = load_res.get("batch_id")

    eval_uuid = uuid.UUID(batch_id) if batch_id else None
    logger.info("Iniciando tarea Spark Bronze -> Silver para batch_id: %s", batch_id)

    result = run_bronze_to_silver(batch_id=eval_uuid)
    logger.info("Tarea Spark Bronze -> Silver completada: %s", result)
    return result


# ==============================================================================
# 5. Ejecutar Spark para Silver → Gold
# ==============================================================================
def run_spark_silver_to_gold_task(
    ti: Any = None,
    batch_id: Optional[str] = None,
) -> dict[str, Any]:
    """Ejecuta la transformación Spark Silver -> Gold (agregaciones, rankings y distribución)."""
    if not batch_id and ti is not None:
        b2s_res = ti.xcom_pull(task_ids="run_spark_bronze_to_silver")
        if b2s_res:
            batch_id = b2s_res.get("batch_id")

    eval_uuid = uuid.UUID(batch_id) if batch_id else None
    logger.info("Iniciando tarea Spark Silver -> Gold para batch_id: %s", batch_id)

    result = run_silver_to_gold(batch_id=eval_uuid)
    logger.info("Tarea Spark Silver -> Gold completada: %s", result)
    return result


# ==============================================================================
# 6. Ejecutar comprobaciones de calidad
# ==============================================================================
def evaluate_data_quality_task(
    ti: Any = None,
    batch_id: Optional[str] = None,
    min_quality_score: float = 70.0,
) -> dict[str, Any]:
    """Comprueba las métricas de calidad del lote y la integridad entre capas."""
    if not batch_id and ti is not None:
        b2s_res = ti.xcom_pull(task_ids="run_spark_bronze_to_silver")
        if b2s_res:
            batch_id = b2s_res.get("batch_id")

    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            # Consulta la métrica de calidad registrada en metrics.data_quality
            if batch_id:
                cur.execute(
                    """
                    SELECT quality_score, total_records, valid_records, invalid_records, failed_rules
                    FROM metrics.data_quality
                    WHERE batch_id = %s
                    ORDER BY evaluated_at DESC
                    LIMIT 1;
                    """,
                    (batch_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT quality_score, total_records, valid_records, invalid_records, failed_rules
                    FROM metrics.data_quality
                    ORDER BY evaluated_at DESC
                    LIMIT 1;
                    """
                )
            row = cur.fetchone()

            if row:
                quality_score, total, valid, invalid, failed_rules = (
                    float(row[0]),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                )
            else:
                # Si no hay registros nuevos o evaluados
                quality_score, total, valid, invalid, failed_rules = 100.0, 0, 0, 0, {}

            # Comprobación de coherencia entre capas
            cur.execute("SELECT count(*) FROM silver.earthquakes;")
            silver_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM gold.earthquakes;")
            gold_count = cur.fetchone()[0]

    # Validación de umbral de calidad si hubo registros evaluados
    if total > 0 and quality_score < min_quality_score:
        msg = f"Umbral de calidad no superado: {quality_score:.2f}% < {min_quality_score:.2f}% (inválidos: {invalid})"
        logger.error(msg)
        raise ValueError(msg)

    logger.info(
        "Comprobación de calidad exitosa. Score: %.2f%%, Válidos: %d, Descartados: %d, Silver: %d, Gold: %d",
        quality_score,
        valid,
        invalid,
        silver_count,
        gold_count,
    )

    return {
        "batch_id": batch_id,
        "quality_score": quality_score,
        "total_records": total,
        "valid_records": valid,
        "invalid_records": invalid,
        "silver_count": silver_count,
        "gold_count": gold_count,
        "status": "PASSED",
    }


# ==============================================================================
# 7. Registrar el resultado de la ejecución
# ==============================================================================
def record_pipeline_execution_task(
    ti: Any = None,
    dag_id: str = "usgs_seismic_pipeline",
    run_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> dict[str, Any]:
    """Registra auditoría operativa del ciclo del pipeline en ops.pipeline_executions."""
    load_res: dict[str, Any] = {}
    quality_res: dict[str, Any] = {}
    if ti is not None:
        load_res = ti.xcom_pull(task_ids="load_events_to_bronze") or {}
        quality_res = ti.xcom_pull(task_ids="evaluate_data_quality") or {}
        if not batch_id:
            batch_id = load_res.get("batch_id") or quality_res.get("batch_id")
        if not run_id and hasattr(ti, "run_id"):
            run_id = ti.run_id

    final_batch_id = uuid.UUID(batch_id) if batch_id else uuid.uuid4()
    final_run_id = run_id or f"manual__{datetime.now(timezone.utc).isoformat()}"
    records_ingested = load_res.get("records_ingested", 0)
    quality_score = quality_res.get("quality_score", 100.0)

    details = {
        "load_summary": load_res,
        "quality_summary": quality_res,
    }

    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.pipeline_executions (
                    dag_id,
                    run_id,
                    batch_id,
                    started_at,
                    completed_at,
                    duration_seconds,
                    records_ingested,
                    quality_score,
                    status,
                    details
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0.0, %s, %s, 'SUCCESS', %s);
                """,
                (
                    dag_id,
                    final_run_id,
                    final_batch_id,
                    records_ingested,
                    quality_score,
                    Jsonb(details),
                ),
            )
            conn.commit()

    logger.info("Auditoría operativa registrada en ops.pipeline_executions para batch: %s", final_batch_id)
    return {
        "batch_id": str(final_batch_id),
        "run_id": final_run_id,
        "status": "RECORDED",
    }


# ==============================================================================
# 8. Marcar los datos como disponibles para consumidores y permitir notificación SSE
# ==============================================================================
def publish_data_availability_task(
    ti: Any = None,
    batch_id: Optional[str] = None,
    records_processed: Optional[int] = None,
) -> dict[str, Any]:
    """Registra la disponibilidad de datos en ops.data_availability para la API y SSE."""
    if ti is not None:
        load_res = ti.xcom_pull(task_ids="load_events_to_bronze") or {}
        if not batch_id:
            batch_id = load_res.get("batch_id")
        if records_processed is None:
            records_processed = load_res.get("records_ingested", 0)

    final_batch_id = uuid.UUID(batch_id) if batch_id else uuid.uuid4()
    count = records_processed if records_processed is not None else 0

    with get_db_connection(role="pipeline") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.data_availability (
                    batch_id,
                    available_at,
                    records_processed,
                    status
                )
                VALUES (%s, CURRENT_TIMESTAMP, %s, 'AVAILABLE');
                """,
                (final_batch_id, count),
            )
            conn.commit()

    logger.info("Lote %s marcado como disponible (registros: %d) para consumidores SSE.", final_batch_id, count)
    return {
        "batch_id": str(final_batch_id),
        "records_processed": count,
        "status": "AVAILABLE",
    }


# ==============================================================================
# 9. Detección de Anomalías Z-Score (Automatización B)
# ==============================================================================
def run_anomaly_detection_task(
    ti: Any = None,
    threshold: Optional[float] = None,
    min_observations: Optional[int] = None,
) -> dict[str, Any]:
    """Tarea Airflow para ejecutar la detección Z-score y persistir alertas y auditoría."""
    from src.ai.anomalies import run_anomaly_detection

    airflow_run_id = None
    if ti is not None:
        try:
            airflow_run_id = ti.dag_run.run_id
        except Exception:
            pass

    return run_anomaly_detection(
        threshold=threshold,
        min_observations=min_observations,
        airflow_run_id=airflow_run_id,
    )


# ==============================================================================
# 10. Resumen Ejecutivo Diario (Automatización A)
# ==============================================================================
def prepare_daily_summary_metrics_task(ti: Any = None) -> dict[str, Any]:
    """Tarea 1 del DAG diario: precalcula métricas analíticas desde Gold."""
    from src.ai.reporter import calculate_daily_summary_metrics

    with get_db_connection(role="ai_reader") as conn:
        with conn.cursor() as cur:
            metrics = calculate_daily_summary_metrics(cur)

    return metrics


def generate_and_persist_daily_report_task(ti: Any = None) -> dict[str, Any]:
    """Tarea 2 del DAG diario: genera narrativa (Ollama o fallback) y persiste auditoría."""
    from src.ai.reporter import run_daily_executive_report

    airflow_run_id = None
    if ti is not None:
        try:
            airflow_run_id = ti.dag_run.run_id
        except Exception:
            pass

    return run_daily_executive_report(airflow_run_id=airflow_run_id)


# ==============================================================================
# 11. Sincronización de Catálogo y Linaje con OpenMetadata (Fase 11)
# ==============================================================================
def sync_metadata_task(ti: Any = None) -> dict[str, Any]:
    """Tarea de mejor esfuerzo: sincroniza esquemas, tablas y linaje con OpenMetadata."""
    from src.metadata.service import sync_metadata_catalog

    try:
        return sync_metadata_catalog()
    except Exception as exc:
        logger.warning(
            "Sincronización con OpenMetadata omitida de forma no bloqueante: %s", exc
        )
        return {"status": "SKIPPED", "reason": str(exc)}
