"""Gestor de ciclo de vida y configuración de SparkSession para la plataforma sísmica."""
from contextlib import contextmanager
import logging
import os
from typing import Generator, Optional
from pyspark.sql import SparkSession
from src.common.config import get_settings


logger = logging.getLogger(__name__)


def _ensure_java_home() -> None:
    """Detecta y configura automáticamente JAVA_HOME si no está exportada en el entorno."""
    if "JAVA_HOME" in os.environ and os.path.exists(os.environ["JAVA_HOME"]):
        return

    # Rutas candidatas comunes (entorno Docker y host local)
    candidates = [
        "/usr/lib/jvm/java-17-openjdk-amd64",
        os.path.expanduser("~/.local/share/jvm/jdk-17.0.21+9-jre"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate) and os.path.exists(os.path.join(candidate, "bin", "java")):
            os.environ["JAVA_HOME"] = candidate
            java_bin = os.path.join(candidate, "bin")
            if java_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{java_bin}:{os.environ.get('PATH', '')}"
            logger.info("JAVA_HOME autodetectada y configurada en: %s", candidate)
            return


def build_spark_session(
    app_name: str = "SeismicPlatformSpark",
    master: Optional[str] = None,
) -> SparkSession:
    """Construye una SparkSession configurada para modo local[*], memoria conservadora y UTC.

    Configuración aplicada:
    - spark.master: local[*] (sin clúster ni overhead distribuido)
    - spark.driver.memory: 1g (conservador para evitar saturar RAM)
    - spark.sql.shuffle.partitions: 4 (adecuado para volumen moderado)
    - spark.sql.session.timeZone: UTC (coherencia en fechas de sismos)
    - spark.jars / extraClassPath: Driver JDBC PostgreSQL
    - spark.ui.enabled: false (sin servidor web superfluo en pipelines batch)
    """
    settings = get_settings()
    _ensure_java_home()

    jar_path = settings.spark.jar_path
    spark_master = master or settings.spark.master

    builder = (
        SparkSession.builder.appName(app_name)
        .master(spark_master)
        .config("spark.driver.memory", settings.spark.driver_memory)
        .config("spark.sql.shuffle.partitions", str(settings.spark.shuffle_partitions))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
    )

    if jar_path and os.path.exists(jar_path):
        logger.info("Configurando classpath del driver JDBC PostgreSQL: %s", jar_path)
        builder = (
            builder.config("spark.jars", jar_path)
            .config("spark.driver.extraClassPath", jar_path)
            .config("spark.executor.extraClassPath", jar_path)
        )
    else:
        logger.warning(
            "Driver JDBC no encontrado en ruta '%s'. Spark operará sin JAR local explícito.",
            jar_path,
        )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


@contextmanager
def get_spark_session(
    app_name: str = "SeismicPlatformSpark",
    master: Optional[str] = None,
) -> Generator[SparkSession, None, None]:
    """Context manager para crear y cerrar limpiamente la SparkSession."""
    spark = build_spark_session(app_name=app_name, master=master)
    try:
        yield spark
    finally:
        logger.info("Cerrando SparkSession y liberando memoria JVM.")
        spark.stop()


def get_jdbc_url(host: Optional[str] = None, port: Optional[int] = None, db: Optional[str] = None) -> str:
    """Construye la URL de conexión JDBC para PostgreSQL."""
    settings = get_settings()
    h = host or settings.db.host
    p = port or settings.db.port
    d = db or settings.db.name
    return f"jdbc:postgresql://{h}:{p}/{d}"


def get_jdbc_properties(role: str = "pipeline") -> dict[str, str]:
    """Genera las propiedades de conexión JDBC según el rol solicitado."""
    settings = get_settings()
    if role == "api_reader":
        user = "api_reader"
        password = settings.db.api_reader_password
    elif role == "ai_reader":
        user = "ai_reader"
        password = settings.db.ai_reader_password
    elif role == "pipeline":
        user = "pipeline"
        password = settings.db.pipeline_password
    else:
        user = settings.db.user
        password = settings.db.password

    return {
        "user": user,
        "password": password,
        "driver": "org.postgresql.Driver",
    }
