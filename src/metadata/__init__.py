"""Módulo de gobernanza, catálogo de datos y linaje con OpenMetadata."""
from src.metadata.client import OpenMetadataClient
from src.metadata.service import sync_metadata_catalog


__all__ = ["OpenMetadataClient", "sync_metadata_catalog"]
