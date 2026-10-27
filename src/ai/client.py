"""Cliente HTTP para Ollama con verificación de modelo, validación Pydantic, reintentos y fallback.

Criterio de Costo Local:
Al ejecutarse en hardware local con Ollama (sin llamadas a APIs de pago), la tarifa
predeterminada por token es 0.0 (AI_COST_PER_TOKEN=0.0). Se permite configurar
una tarifa arbitraria para auditoría de recursos de cómputo en la variable AI_COST_PER_TOKEN.
"""
from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Optional, Type

import httpx
from pydantic import BaseModel
from src.ai.prompts import parse_and_validate_json_response
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
    validated_data: Optional[Any] = None
    validation_error: Optional[str] = None


class OllamaClient:
    """Cliente para interactuar con Ollama o degradar gracefully a fallback determinista."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: int = 2,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.ai.ollama_base_url).rstrip("/")
        self.model = model or settings.ai.model
        self.timeout = timeout_seconds or settings.ai.timeout_seconds
        self.cost_per_token = settings.ai.cost_per_token
        self.max_retries = max(1, max_retries)

    def is_model_ready(self, auto_pull: bool = False) -> bool:
        """Verifica si el servicio Ollama responde y si el modelo está descargado y listo."""
        try:
            with httpx.Client(timeout=min(self.timeout, 5)) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return False

                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                # Coincidencia con nombre base o etiqueta
                has_model = any(
                    m == self.model or m.startswith(f"{self.model}:") or self.model.startswith(f"{m}:")
                    for m in models if m
                )

                if has_model:
                    return True

                if auto_pull:
                    logger.info("Modelo %s no encontrado localmente. Iniciando pull...", self.model)
                    pull_resp = client.post(
                        f"{self.base_url}/api/pull",
                        json={"name": self.model, "stream": False},
                        timeout=300,
                    )
                    return pull_resp.status_code == 200

                return False
        except Exception as exc:
            logger.debug("Ollama no está disponible para verificación de modelo: %s", exc)
            return False

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        response_model: Optional[Type[BaseModel]] = None,
        authorized_data: Optional[dict[str, Any]] = None,
        fallback_fn: Optional[Callable[[dict[str, Any]], str]] = None,
        fallback_data: Optional[dict[str, Any]] = None,
    ) -> AIGenerationResult:
        """Invoca Ollama con reintentos y validación Pydantic. Si falla o se rechaza, activa fallback."""
        start_time = time.time()
        endpoint = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json" if response_model else None,
        }
        if system:
            payload["system"] = system

        last_error = ""

        # Intentos acotados
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(endpoint, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                raw_text = data.get("response", "").strip()
                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)
                total_tokens = prompt_tokens + completion_tokens
                cost = total_tokens * self.cost_per_token
                latency_ms = int((time.time() - start_time) * 1000)

                # Si se especificó un esquema Pydantic, validar estructura y consistencia
                if response_model and authorized_data is not None:
                    validated_obj, is_valid, error_msg = parse_and_validate_json_response(
                        raw_text=raw_text,
                        model_cls=response_model,
                        authorized_data=authorized_data,
                    )

                    if not is_valid:
                        last_error = error_msg or "Validación fallida"
                        logger.warning(
                            "Intento %d/%d: Respuesta de Ollama rechazada por validación: %s",
                            attempt,
                            self.max_retries,
                            last_error,
                        )
                        # Reintentar si quedan intentos disponibles
                        continue

                    # Si el modelo tiene método to_markdown (como DailyReportStructuredOutput), usarlo
                    final_text = (
                        validated_obj.to_markdown()
                        if hasattr(validated_obj, "to_markdown")
                        else getattr(validated_obj, "explanation", raw_text)
                    )

                    return AIGenerationResult(
                        text=final_text,
                        model_name=self.model,
                        status="SUCCESS",
                        used_fallback=False,
                        input_tokens=prompt_tokens,
                        output_tokens=completion_tokens,
                        latency_ms=latency_ms,
                        estimated_cost=cost,
                        validated_data=validated_obj,
                    )

                # Respuesta de texto plano válida
                if not raw_text:
                    raise ValueError("Ollama retornó una respuesta de texto vacía")

                return AIGenerationResult(
                    text=raw_text,
                    model_name=self.model,
                    status="SUCCESS",
                    used_fallback=False,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    estimated_cost=cost,
                )

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Intento %d/%d falló conectando a Ollama (%s).",
                    attempt,
                    self.max_retries,
                    last_error,
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * attempt)

        # Si se agotaron los reintentos o la respuesta fue rechazada por inconsistencias:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.warning(
            "Ollama no disponible o rechazado tras %d intentos (%s). Activando fallback determinista.",
            self.max_retries,
            last_error,
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
            validation_error=last_error,
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
