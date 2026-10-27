"""Módulo de conexión a PostgreSQL usando psycopg 3."""
from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg import Connection
from src.common.config import get_settings


@contextmanager
def get_db_connection(role: str = "pipeline") -> Generator[Connection, None, None]:
    """Provee una conexión contextual a PostgreSQL según el rol solicitado.

    Roles soportados:
    - 'pipeline': Acceso completo para Airflow / Spark.
    - 'api_reader': Solo lectura sobre Gold y tablas operativas.
    - 'ai_reader': Solo lectura sobre agregados analíticos.
    """
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

    conn = psycopg.connect(
        host=settings.db.host,
        port=settings.db.port,
        dbname=settings.db.name,
        user=user,
        password=password,
    )
    try:
        yield conn
    finally:
        conn.close()
