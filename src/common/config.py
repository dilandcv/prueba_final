"""Configuración centralizada de la plataforma cargada desde variables de entorno."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import socket


def _load_env_file() -> None:
    """Carga variables desde el archivo .env si existe y no están definidas."""
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v


_load_env_file()


def _resolve_db_host_port() -> tuple[str, int]:
    """Resuelve dinámicamente host y puerto según se ejecute en Docker o en host local."""
    configured_host = os.getenv("POSTGRES_HOST", "postgres")
    configured_port = int(os.getenv("POSTGRES_PORT", "5432"))
    if configured_host == "postgres":
        try:
            socket.gethostbyname("postgres")
            return configured_host, configured_port
        except (socket.gaierror, OSError):
            host_port = int(os.getenv("POSTGRES_HOST_PORT", "5433"))
            return "localhost", host_port
    return configured_host, configured_port


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = field(default_factory=lambda: _resolve_db_host_port()[0])
    port: int = field(default_factory=lambda: _resolve_db_host_port()[1])
    name: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "seismic_platform"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres_admin"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres_example_password"))
    pipeline_password: str = field(default_factory=lambda: os.getenv("POSTGRES_PIPELINE_PASSWORD", "pipeline_example_password"))
    api_reader_password: str = field(default_factory=lambda: os.getenv("POSTGRES_API_READER_PASSWORD", "api_reader_example_password"))
    ai_reader_password: str = field(default_factory=lambda: os.getenv("POSTGRES_AI_READER_PASSWORD", "ai_reader_example_password"))


@dataclass(frozen=True)
class USGSSettings:
    api_base_url: str = field(default_factory=lambda: os.getenv("USGS_API_BASE_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query"))
    min_magnitude: float = field(default_factory=lambda: float(os.getenv("USGS_MIN_MAGNITUDE", "2.5")))
    ingest_interval_minutes: int = field(default_factory=lambda: int(os.getenv("INGEST_INTERVAL_MINUTES", "15")))
    initial_lookback_days: int = field(default_factory=lambda: int(os.getenv("INITIAL_LOOKBACK_DAYS", "7")))
    request_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_REQUEST_RETRIES", "3")))


@dataclass(frozen=True)
class SparkSettings:
    master: str = field(default_factory=lambda: os.getenv("SPARK_MASTER", "local[*]"))
    driver_memory: str = field(default_factory=lambda: os.getenv("SPARK_DRIVER_MEMORY", "1g"))
    shuffle_partitions: int = field(default_factory=lambda: int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "4")))
    jar_path: str = field(default_factory=lambda: os.getenv(
        "SPARK_JDBC_JAR",
        "/opt/airflow/jars/postgresql-42.7.3.jar" if os.path.exists("/opt/airflow/jars/postgresql-42.7.3.jar")
        else str(Path(__file__).resolve().parent.parent.parent / "jars" / "postgresql-42.7.3.jar")
    ))


@dataclass(frozen=True)
class APISettings:
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    cors_origins: list[str] = field(default_factory=lambda: os.getenv("API_CORS_ORIGINS", "http://localhost:3000").split(","))


@dataclass(frozen=True)
class AISettings:
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2:1b"))
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("AI_TIMEOUT_SECONDS", "15")))
    cost_per_token: float = field(default_factory=lambda: float(os.getenv("AI_COST_PER_TOKEN", "0.0")))
    anomaly_threshold: float = field(default_factory=lambda: float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0")))
    anomaly_min_observations: int = field(default_factory=lambda: int(os.getenv("ANOMALY_MIN_OBSERVATIONS", "24")))


@dataclass(frozen=True)
class Settings:
    db: DatabaseSettings = field(default_factory=DatabaseSettings)
    usgs: USGSSettings = field(default_factory=USGSSettings)
    spark: SparkSettings = field(default_factory=SparkSettings)
    api: APISettings = field(default_factory=APISettings)
    ai: AISettings = field(default_factory=AISettings)


def get_settings() -> Settings:
    """Devuelve la instancia de configuración actual."""
    return Settings()
