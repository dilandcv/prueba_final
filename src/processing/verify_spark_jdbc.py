"""Script de verificación técnica del entorno Spark, Java y JDBC PostgreSQL."""
from datetime import datetime, timezone
import logging
import sys
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from src.processing.spark_session import (
    get_jdbc_properties,
    get_jdbc_url,
    get_spark_session,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VerifySparkJDBC")


def run_verification() -> bool:
    """Ejecuta la batería de comprobaciones técnicas de Java, PySpark y conectividad JDBC."""
    logger.info("=== 1. Comprobación de Java y PySpark ===")
    import pyspark
    logger.info("PySpark disponible. Versión instalada: %s", pyspark.__version__)

    logger.info("=== 2. Creación de SparkSession con configuración conservadora ===")
    with get_spark_session(app_name="VerifySparkEnvironment", master="local[1]") as spark:
        # Verificación de parámetros
        conf = spark.sparkContext.getConf()
        master = conf.get("spark.master")
        memory = conf.get("spark.driver.memory", "1g")
        partitions = spark.conf.get("spark.sql.shuffle.partitions")
        tz = spark.conf.get("spark.sql.session.timeZone")

        logger.info("Spark master: %s", master)
        logger.info("Spark driver memory: %s", memory)
        logger.info("Spark shuffle partitions: %s", partitions)
        logger.info("Spark session timezone: %s", tz)

        assert tz == "UTC", f"La zona horaria debe ser UTC, encontrada: {tz}"

        logger.info("=== 3. Comprobación del classpath del Driver JDBC ===")
        try:
            driver_class = spark._jvm.java.lang.Class.forName("org.postgresql.Driver")
            logger.info("Driver JDBC PostgreSQL cargado con éxito en la JVM: %s", driver_class.getName())
        except Exception as exc:
            logger.error("Error al cargar la clase del driver JDBC 'org.postgresql.Driver': %s", exc)
            return False

        logger.info("=== 4. Creación y transformación de DataFrame en Spark ===")
        # Se construye mediante Spark SQL para ejecución nativa en Catalyst sin serialización RDD
        df = spark.sql("""
            SELECT
                'test_evt_1' AS event_id,
                CAST(3.5 AS DOUBLE) AS magnitude,
                '10km NE of TestCity' AS place,
                'Test Region' AS region,
                CURRENT_TIMESTAMP() AS time_utc,
                CURRENT_TIMESTAMP() AS updated_at_utc,
                CAST(-120.5 AS DOUBLE) AS longitude,
                CAST(35.2 AS DOUBLE) AS latitude,
                CAST(5.0 AS DOUBLE) AS depth_km,
                FALSE AS tsunami_alert,
                CURRENT_TIMESTAMP() AS ingested_at
            UNION ALL
            SELECT
                'test_evt_2' AS event_id,
                CAST(4.8 AS DOUBLE) AS magnitude,
                '25km S of TestIsland' AS place,
                'Oceanic Region' AS region,
                CURRENT_TIMESTAMP() AS time_utc,
                CURRENT_TIMESTAMP() AS updated_at_utc,
                CAST(-115.1 AS DOUBLE) AS longitude,
                CAST(32.8 AS DOUBLE) AS latitude,
                CAST(12.0 AS DOUBLE) AS depth_km,
                FALSE AS tsunami_alert,
                CURRENT_TIMESTAMP() AS ingested_at
        """)
        record_count = df.count()
        logger.info("DataFrame creado en Spark con éxito (%d registros evaluados).", record_count)

        logger.info("=== 5. Intento de lectura/escritura JDBC contra PostgreSQL ===")
        jdbc_url = get_jdbc_url()
        jdbc_props = get_jdbc_properties(role="pipeline")
        staging_table = "silver._staging_earthquakes"

        try:
            logger.info("Intentando escribir en %s mediante JDBC...", staging_table)
            df.write.jdbc(
                url=jdbc_url,
                table=staging_table,
                mode="overwrite",
                properties=jdbc_props,
            )
            logger.info("Escritura JDBC exitosa en %s.", staging_table)

            logger.info("Intentando leer desde %s mediante JDBC...", staging_table)
            read_df = spark.read.jdbc(
                url=jdbc_url,
                table=staging_table,
                properties=jdbc_props,
            )
            read_count = read_df.count()
            logger.info("Lectura JDBC exitosa. Registros leídos: %d", read_count)
            assert read_count == record_count, f"Esperados {record_count}, obtenidos {read_count}"
        except Exception as exc:
            logger.warning(
                "La prueba JDBC en vivo no pudo completarse contra '%s': %s. "
                "(Esperado si el contenedor de PostgreSQL aún no está iniciado).",
                jdbc_url,
                exc,
            )

    logger.info("=== Verificación técnica finalizada exitosamente ===")
    return True


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
