"""Registro y despacho centralizado de herramientas analíticas y documentales."""
import logging
from typing import Any, Callable

from src.ai.rag import search_project_documentation
from src.ai.tools.seismic_tools import (
    compare_earthquake_periods,
    get_anomaly_alerts,
    get_data_quality_metrics,
    get_earthquake_statistics,
    get_earthquakes_by_region,
    get_latest_earthquakes,
    get_magnitude_distribution,
    get_strongest_earthquake,
)

logger = logging.getLogger(__name__)

# Catálogo explícito de herramientas autorizadas (White-list)
TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_strongest_earthquake": get_strongest_earthquake,
    "get_earthquake_statistics": get_earthquake_statistics,
    "get_latest_earthquakes": get_latest_earthquakes,
    "get_earthquakes_by_region": get_earthquakes_by_region,
    "get_magnitude_distribution": get_magnitude_distribution,
    "compare_earthquake_periods": compare_earthquake_periods,
    "get_anomaly_alerts": get_anomaly_alerts,
    "get_data_quality_metrics": get_data_quality_metrics,
    "search_project_documentation": search_project_documentation,
}


def execute_tool(name: str, cur: Any, **kwargs) -> Any:
    """Ejecuta una herramienta de forma segura verificando su presencia en el registro."""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Herramienta no autorizada o no registrada: '{name}'")

    tool_fn = TOOL_REGISTRY[name]
    logger.debug("Ejecutando herramienta '%s' con parámetros: %s", name, kwargs)
    return tool_fn(cur, **kwargs)
