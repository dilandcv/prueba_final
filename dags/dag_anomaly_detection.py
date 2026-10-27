"""DAG de Airflow para la Detección Horaria de Anomalías Sísmicas mediante Z-Score.

Automatización B:
1. Consulta la tabla gold.hourly_regional_stats mediante el rol restringido ai_reader.
2. Calcula mediante SQL el Z-Score por región sobre los conteos horarios de eventos.
3. Filtra regiones que superen el umbral configurable y cumplan el mínimo de observaciones.
4. Genera explicaciones narrativas breves (con fallback determinista) y persiste
   las alertas en ops.anomaly_alerts y la auditoría en ops.ai_executions mediante el rol pipeline.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.common.config import get_settings
from src.pipeline.tasks import run_anomaly_detection_task


settings = get_settings()

DAG_DOC = """
# Detección Estadística de Anomalías Sísmicas (Z-Score)

Este DAG orquesta la identificación periódica de frecuencias inusuales de sismos por región:

- **Frecuencia**: Horaria (`0 * * * *`).
- **Concurrencia**: `max_active_runs=1` para evitar alertas duplicadas.
- **Catchup**: `catchup=False`.
- **Lógica Matemática**: Z-Score muestral calculado in-database en PostgreSQL mediante funciones de ventana.
- **Idempotencia**: Verificación de existencia previa antes de insertar en `ops.anomaly_alerts`.
- **Aviso Metodológico**: Este cálculo identifica exclusivamente desviaciones estadísticas observadas
  respecto a la media histórica reciente; **NO es un pronóstico ni predicción de terremotos**.
"""

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=10),
}

with DAG(
    dag_id="seismic_anomaly_detection",
    default_args=default_args,
    description="Detección de frecuencias anómalas por región mediante Z-Score y explicaciones con fallback",
    doc_md=DAG_DOC,
    schedule_interval="0 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["seismic", "gold", "anomalies", "zscore", "ai"],
) as dag:

    detect_anomalies = PythonOperator(
        task_id="detect_and_alert_anomalies",
        python_callable=run_anomaly_detection_task,
    )
