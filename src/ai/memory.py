"""Gestor de memoria conversacional acotada y resolución de contexto."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ConversationContext:
    """Estado estructurado de una conversación en curso."""
    last_region: Optional[str] = None
    last_start_time: Optional[datetime] = None
    last_end_time: Optional[datetime] = None
    last_min_magnitude: Optional[float] = None
    last_tool_called: Optional[str] = None
    turns_count: int = 0

    def update(self, tool_name: Optional[str], params: dict[str, Any]) -> None:
        """Actualiza el contexto activo con los parámetros del turno actual."""
        self.turns_count += 1
        if tool_name:
            self.last_tool_called = tool_name
        if params.get("region"):
            self.last_region = params["region"]
        if params.get("start_time"):
            self.last_start_time = params["start_time"]
        if params.get("end_time"):
            self.last_end_time = params["end_time"]
        if params.get("min_magnitude") is not None:
            self.last_min_magnitude = params["min_magnitude"]

    def apply_to_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Aplica valores heredados a parámetros faltantes en consultas de seguimiento."""
        merged = dict(params)
        if not merged.get("region") and self.last_region:
            merged["region"] = self.last_region
        if not merged.get("start_time") and self.last_start_time:
            merged["start_time"] = self.last_start_time
            merged["end_time"] = self.last_end_time or datetime.now(timezone.utc)
        return merged
