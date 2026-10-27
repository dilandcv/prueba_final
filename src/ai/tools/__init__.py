"""Herramientas analíticas y de catálogo para el agente de IA."""
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
from src.ai.tools.registry import TOOL_REGISTRY, execute_tool

__all__ = [
    "compare_earthquake_periods",
    "get_anomaly_alerts",
    "get_data_quality_metrics",
    "get_earthquake_statistics",
    "get_earthquakes_by_region",
    "get_latest_earthquakes",
    "get_magnitude_distribution",
    "get_strongest_earthquake",
    "TOOL_REGISTRY",
    "execute_tool",
]
