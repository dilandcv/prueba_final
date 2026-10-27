"""Módulo de observabilidad, trazabilidad y registro de métricas del agente."""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional

from src.common.db import get_db_connection

logger = logging.getLogger(__name__)


def record_agent_trace(
    intent: str,
    tools_called: list[str],
    latency_ms: int,
    used_fallback: bool,
    model_name: str,
    rejection_reason: Optional[str] = None,
    status: str = "SUCCESS",
) -> None:
    """Registra una traza de ejecución del agente en ops.ai_executions de forma segura y no bloqueante."""
    automation_type = f"AGENT_{intent}" if intent else "AGENT_INTERACTION"
    if rejection_reason:
        automation_type += f"_{rejection_reason}"

    try:
        with get_db_connection(role="pipeline") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.ai_executions (
                        executed_at,
                        automation_type,
                        prompt_version,
                        model_name,
                        status,
                        input_tokens,
                        output_tokens,
                        latency_ms,
                        estimated_cost,
                        used_fallback,
                        airflow_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        datetime.now(timezone.utc),
                        automation_type[:50],
                        "agent_v2",
                        model_name[:50],
                        status[:20],
                        len(tools_called) * 50,  # Estimación representativa
                        100,
                        latency_ms,
                        0.0,
                        used_fallback,
                        json.dumps({"tools": tools_called, "intent": intent}),
                    ),
                )
                conn.commit()
    except Exception as exc:
        logger.debug("No se pudo persistir la traza de observabilidad (no bloqueante): %s", exc)
