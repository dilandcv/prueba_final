"""Módulo de procesamiento y transformaciones con Apache Spark."""
from src.processing.spark_session import (
    build_spark_session,
    get_jdbc_properties,
    get_jdbc_url,
    get_spark_session,
)

__all__ = [
    "build_spark_session",
    "get_spark_session",
    "get_jdbc_url",
    "get_jdbc_properties",
    "parse_and_normalize_bronze",
    "deduplicate_events",
    "run_bronze_to_silver",
    "build_gold_earthquakes",
    "build_hourly_regional_stats",
    "build_magnitude_distribution",
    "build_regional_ranking_24h",
    "run_silver_to_gold",
]


def __getattr__(name: str):
    if name in {"parse_and_normalize_bronze", "deduplicate_events", "run_bronze_to_silver"}:
        import src.processing.bronze_to_silver as b2s

        return getattr(b2s, name)
    if name in {
        "build_gold_earthquakes",
        "build_hourly_regional_stats",
        "build_magnitude_distribution",
        "build_regional_ranking_24h",
        "run_silver_to_gold",
    }:
        import src.processing.silver_to_gold as s2g

        return getattr(s2g, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
