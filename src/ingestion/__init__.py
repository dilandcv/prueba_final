"""Módulo de ingesta de datos de la API del USGS."""
from src.ingestion.usgs_client import USGSAPIError, USGSClient

__all__ = ["USGSClient", "USGSIngestionService", "USGSAPIError"]


def __getattr__(name: str):
    if name == "USGSIngestionService":
        from src.ingestion.service import USGSIngestionService

        return USGSIngestionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
