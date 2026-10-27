"""Cliente HTTP para Ollama con fallback determinista y registro de auditoría."""
from dataclasses import dataclass
import logging
import time
from typing import Any, Optional

import httpx
from src.common.config import get_settings


logger = logging.getLogger(__name__)


@dataclass
class AIGenerationResult:
    """Resultado estructurado de una invocación de IA o fallback determinista."""
    text: str
    model_name: str
    status: str  # 'SUCCESS', 'FALLBACK', 'ERROR'
    used_fallback: bool
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    estimated_cost: float = 0.0


class OllamaClient:
    """Cliente para interactuar con Ollama o degradar gracefully a fallback determinista."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.ai.ollama_base_url).rstrip("/")
        self.model = model or settings.ai.model
        self.timeout = timeout_seconds or settings.ai.timeout_seconds
        self.cost_per_token = settings.ai.cost_per_token

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        fallback_fn: Optional[Any] = None,
        fallback_data: Optional[dict[str, Any]] = None,
    ) -> AIGenerationResult:
        """Intenta invocar Ollama vía HTTP. Si falla o no está disponible, ejecuta el fallback."""
        start_time = time.time()
        endpoint = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload)
                resp.raise_for_status()
                data = resp.json()

            latency_ms = int((time.time() - start_time) * 1000)
            text = data.get("response", "").strip()
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
            total_tokens = prompt_tokens + completion_tokens
            cost = total_tokens * self.cost_per_token

            if not text:
                raise ValueError("Ollama retornó una respuesta vacía")

            return AIGenerationResult(
                text=text,
                model_name=self.model,
                status="SUCCESS",
                used_fallback=False,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                latency_ms=latency_ms,
                estimated_cost=cost,
            )

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Ollama no disponible o falló en %s (%s). Activando fallback determinista.",
                endpoint,
                exc,
            )

            fallback_text = ""
            if fallback_fn and fallback_data is not None:
                try:
                    fallback_text = fallback_fn(fallback_data)
                except Exception as fb_err:
                    logger.error("Error al ejecutar función de fallback: %s", fb_err)
                    fallback_text = "Explicación no disponible por error en módulo de respaldo."

            return AIGenerationResult(
                text=fallback_text,
                model_name="deterministic_fallback",
                status="FALLBACK",
                used_fallback=True,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                estimated_cost=0.0,
            )


def record_ai_execution(
    cur: Any,
    result: AIGenerationResult,
    automation_type: str,
    prompt_version: str,
    airflow_run_id: Optional[str] = None,
) -> int:
    """Registra la auditoría de ejecución en ops.ai_executions y devuelve su ID."""
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
        ) VALUES (
            CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id;
        """,
        (
            automation_type,
            prompt_version,
            result.model_name,
            result.status,
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
            result.estimated_cost,
            result.used_fallback,
            airflow_run_id,
        ),
    )
    row = cur.fetchone()
    return row[0] if row else 0
