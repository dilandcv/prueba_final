"""Módulo de reglas y cálculo de métricas de calidad de datos."""
from src.quality.rules import QualitySummary, evaluate_quality, get_quality_conditions

__all__ = ["evaluate_quality", "get_quality_conditions", "QualitySummary"]
