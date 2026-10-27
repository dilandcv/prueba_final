"""Pruebas de cumplimiento de reglas arquitectónicas obligatorias."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_forbidden_libraries_not_in_requirements():
    """Garantiza que pandas, polars o dask no estén listadas en requirements.txt."""
    req_path = PROJECT_ROOT / "requirements.txt"
    assert req_path.exists(), "requirements.txt debe existir"
    
    content = req_path.read_text(encoding="utf-8").lower()
    forbidden = ["pandas", "polars", "dask"]
    
    for lib in forbidden:
        # Verifica que ninguna línea contenga el paquete como dependencia
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                assert lib not in line, f"Dependencia prohibida detectada: {lib} en '{line}'"


def test_required_directory_structure():
    """Garantiza que la estructura modular requerida esté presente."""
    required_directories = [
        "src/common",
        "src/ingestion",
        "src/processing",
        "src/quality",
        "src/ai",
        "src/api",
        "src/api/routers",
        "dags",
        "prompts",
        "sql",
        "docs",
        "frontend",
        "tests",
        "tests/fixtures",
    ]
    for dir_rel in required_directories:
        dir_path = PROJECT_ROOT / dir_rel
        assert dir_path.is_dir(), f"El directorio requerido '{dir_rel}' no existe."


def test_env_example_contains_all_core_keys():
    """Verifica que .env.example incluya todas las configuraciones esenciales sin secretos reales."""
    env_example = PROJECT_ROOT / ".env.example"
    assert env_example.exists(), ".env.example debe existir"
    
    content = env_example.read_text(encoding="utf-8")
    expected_keys = [
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_PIPELINE_PASSWORD",
        "POSTGRES_API_READER_PASSWORD",
        "POSTGRES_AI_READER_PASSWORD",
        "USGS_API_BASE_URL",
        "USGS_MIN_MAGNITUDE",
        "INGEST_INTERVAL_MINUTES",
        "SPARK_MASTER",
        "SPARK_DRIVER_MEMORY",
        "API_PORT",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
    ]
    for key in expected_keys:
        assert f"{key}=" in content, f"La clave '{key}' debe estar documentada en .env.example"
