"""DAG de Airflow para la generación del Resumen Ejecutivo Diario de Actividad Sísmica.

Automatización A:
1. prepare_daily_metrics: Precalcula deterministamente en SQL todas las cifras,
   tendencias, ranking de regiones y eventos destacados sobre la capa Gold.
2. generate_and_persist_report: Invoca al modelo de IA local (Ollama) para redactar
   el informe ejecutivo en lenguaje natural. Si Ollama no está disponible o falla,
   activa de forma transparente el mecanismo de fallback determinista y registra
   la auditoría completa en ops.ai_executions.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.common.config import get_settings
from src.pipeline.tasks import (
    generate_and_persist_daily_report_task,
    prepare_daily_summary_metrics_task,
)


settings = get_settings()

DAG_DOC = """
# Resumen Ejecutivo Diario de Actividad Sísmica (USGS Gold)

Este DAG orquesta la generación diaria del informe ejecutivo consolidado:

- **Frecuencia**: Diario (`@daily` a las 06:00 UTC).
- **Concurrencia**: `max_active_runs=1` para evitar ejecuciones concurrentes.
- **Catchup**: `catchup=False` para evitar ejecuciones pasadas innecesarias.
- **Segregación de Roles**: Consulta datos con rol de solo lectura `ai_reader` y registra
  auditorías operativas con rol `pipeline`.
- **Determinismo y Fallback**: Todas las cifras y rankings son precalculados en SQL antes
  de la redacción. Si Ollama no responde, se genera un reporte determinista validado.

### Flujo de Tareas
1. `prepare_daily_metrics`: Extrae y consolida métricas de las últimas 24h desde Gold.
2. `generate_and_persist_report`: Redacta narrativa (Ollama o Fallback) y persiste trazabilidad en `ops.ai_executions`.
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
    dag_id="daily_seismic_executive_report",
    default_args=default_args,
    description="Resumen ejecutivo diario con métricas precalculadas y redacción con fallback",
    doc_md=DAG_DOC,
    schedule_interval="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["seismic", "gold", "ai", "executive_report"],
) as dag:

    prepare_metrics = PythonOperator(
        task_id="prepare_daily_metrics",
        python_callable=prepare_daily_summary_metrics_task,
    )

    generate_report = PythonOperator(
        task_id="generate_and_persist_report",
        python_callable=generate_and_persist_daily_report_task,
    )

    prepare_metrics >> generate_report
