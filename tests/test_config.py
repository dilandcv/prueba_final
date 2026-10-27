"""Pruebas unitarias para la configuración centralizada."""
from src.common.config import get_settings


def test_default_settings(default_settings):
    """Verifica que las configuraciones por defecto correspondan a los valores esperados."""
    assert default_settings.db.port == 5432
    assert default_settings.db.name == "seismic_platform"
    assert default_settings.usgs.min_magnitude == 2.5
    assert default_settings.usgs.ingest_interval_minutes == 15
    assert default_settings.spark.master == "local[*]"
    assert default_settings.spark.driver_memory == "1g"
    assert default_settings.ai.model == "llama3.2:1b"
    assert default_settings.ai.anomaly_threshold == 3.0


def test_environment_override(clean_env):
    """Verifica que las variables de entorno sobreescriban los valores por defecto."""
    settings = get_settings()
    assert settings.db.host == "test-postgres"
    assert settings.db.port == 5433
    assert settings.db.name == "test_db"
    assert settings.usgs.min_magnitude == 3.0
    assert settings.usgs.ingest_interval_minutes == 10
    assert settings.spark.master == "local[2]"
    assert settings.ai.model == "test-model"
