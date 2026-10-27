"""DAG principal de orquestación de la plataforma de análisis sísmico del USGS.

Recorrido de ejecución:
1. determine_query_interval: Determina el intervalo de consulta y genera batch_id.
2. extract_usgs_events: Extrae eventos sísmicos de la API pública del USGS.
3. load_events_to_bronze: Ingesta append-only en PostgreSQL (bronze.earthquakes) y actualiza watermark.
4. run_spark_bronze_to_silver: PySpark limpia, valida reglas de calidad y hace upsert a silver.earthquakes.
5. run_spark_silver_to_gold: PySpark genera analítica en gold (agregaciones, distribución y ranking).
6. evaluate_data_quality: Verifica que el lote supere los umbrales de calidad y consistencia.
7. record_pipeline_execution: Registra auditoría operativa en ops.pipeline_executions.
8. publish_data_availability: Notifica disponibilidad en ops.data_availability para FastAPI y SSE.
"""
from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.common.config import get_settings
from src.pipeline.tasks import (
    determine_query_interval,
    evaluate_data_quality_task,
    extract_usgs_events,
    load_events_to_bronze,
    publish_data_availability_task,
    record_pipeline_execution_task,
    run_spark_bronze_to_silver_task,
    run_spark_silver_to_gold_task,
)


settings = get_settings()

DAG_DOC = """
# Pipeline de Ingesta y Procesamiento Sísmico (USGS -> Medallion)

Este DAG orquesta el flujo de datos de la plataforma de análisis sísmico:

- **Frecuencia**: Cada `INGEST_INTERVAL_MINUTES` (por defecto 15 minutos).
- **Concurrencia**: `max_active_runs=1` para evitar solapamientos entre ejecuciones periódicas.
- **Catchup**: `catchup=False` para evitar reprocesamientos innecesarios en arranques iniciales.
- **Arranque**: `is_paused_upon_creation=False` para arranque automático tras inicialización.
- **Idempotencia**: Garantizada mediante deduplicación en Bronze, staging y upsert SQL en Silver y Gold.

### Orden de Tareas
1. `determine_query_interval`: Determinar intervalo inicial o incremental.
2. `extract_usgs_events`: Petición HTTP a la API del USGS con reintentos progresivos.
3. `load_events_to_bronze`: Ingesta append-only en `bronze.earthquakes`.
4. `run_spark_bronze_to_silver`: Transformación Spark Bronze -> Silver y descarte en memoria.
5. `run_spark_silver_to_gold`: Transformación Spark Silver -> Gold (agregaciones, ranking, distribución).
6. `evaluate_data_quality`: Comprobación de umbrales de calidad e integridad de datos.
7. `record_pipeline_execution`: Registro en `ops.pipeline_executions`.
8. `publish_data_availability`: Publicación en `ops.data_availability` para Server-Sent Events (SSE).
"""

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": settings.usgs.max_retries,
    "retry_delay": timedelta(seconds=20),
    "execution_timeout": timedelta(minutes=15),
}

with DAG(
    dag_id="usgs_seismic_pipeline",
    default_args=default_args,
    description="Pipeline Medallón continuo de eventos sísmicos USGS (Bronze -> Silver -> Gold)",
    doc_md=DAG_DOC,
    schedule=timedelta(minutes=settings.usgs.ingest_interval_minutes),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["seismic", "usgs", "medallion", "spark", "gold"],
) as dag:

    # 1. Determinar el intervalo de consulta
    t1_determine_interval = PythonOperator(
        task_id="determine_query_interval",
        python_callable=determine_query_interval,
        doc_md="Consulta ops.ingestion_watermark y determina si es carga inicial o incremental.",
    )

    # 2. Extraer eventos de la API
    t2_extract_events = PythonOperator(
        task_id="extract_usgs_events",
        python_callable=extract_usgs_events,
        doc_md="Descarga eventos GeoJSON desde la API oficial de USGS.",
    )

    # 3. Cargar eventos en Bronze
    t3_load_bronze = PythonOperator(
        task_id="load_events_to_bronze",
        python_callable=load_events_to_bronze,
        doc_md="Inserta eventos en bronze.earthquakes preservando payload completo y actualiza watermark.",
    )

    # 4. Ejecutar Spark para Bronze → Silver
    t4_spark_b2s = PythonOperator(
        task_id="run_spark_bronze_to_silver",
        python_callable=run_spark_bronze_to_silver_task,
        doc_md="Valida Java/JDBC, ejecuta PySpark Bronze -> Silver, evalúa calidad y realiza upsert.",
    )

    # 5. Ejecutar Spark para Silver → Gold
    t5_spark_s2g = PythonOperator(
        task_id="run_spark_silver_to_gold",
        python_callable=run_spark_silver_to_gold_task,
        doc_md="Ejecuta PySpark Silver -> Gold para calcular métricas horarias, rankings y distribución.",
    )

    # 6. Ejecutar comprobaciones de calidad
    t6_check_quality = PythonOperator(
        task_id="evaluate_data_quality",
        python_callable=evaluate_data_quality_task,
        doc_md="Comprueba puntaje de calidad registrado y coherencia entre esquemas Silver y Gold.",
    )

    # 7. Registrar el resultado de la ejecución
    t7_record_metrics = PythonOperator(
        task_id="record_pipeline_execution",
        python_callable=record_pipeline_execution_task,
        doc_md="Persiste auditoría consolidada de la corrida en ops.pipeline_executions.",
    )

    # 8. Marcar los datos como disponibles para los consumidores y permitir la notificación SSE
    t8_publish_availability = PythonOperator(
        task_id="publish_data_availability",
        python_callable=publish_data_availability_task,
        doc_md="Registra disponibilidad en ops.data_availability habilitando notificación SSE en FastAPI.",
    )

    # Flujo secuencial estricto requerido
    (
        t1_determine_interval
        >> t2_extract_events
        >> t3_load_bronze
        >> t4_spark_b2s
        >> t5_spark_s2g
        >> t6_check_quality
        >> t7_record_metrics
        >> t8_publish_availability
    )
