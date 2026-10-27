"""Configuración y fixtures globales de pytest."""
import os
import pytest
from src.common.config import Settings, get_settings


@pytest.fixture
def clean_env(monkeypatch):
    """Fixture para aislar variables de entorno durante las pruebas."""
    monkeypatch.setenv("POSTGRES_HOST", "test-postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("USGS_MIN_MAGNITUDE", "3.0")
    monkeypatch.setenv("INGEST_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("SPARK_MASTER", "local[2]")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    return os.environ


@pytest.fixture
def default_settings() -> Settings:
    """Fixture que devuelve la configuración por defecto."""
    return get_settings()
