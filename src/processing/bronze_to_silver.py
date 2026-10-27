"""Procesamiento de datos Bronze a Silver utilizando Apache Spark (PySpark)."""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional
import uuid
from psycopg import Connection
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    coalesce,
    col,
    element_at,
    from_json,
    from_unixtime,
    round as spark_round,
    row_number,
    split,
    to_timestamp,
    trim,
    when,
)
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window
from src.common.config import get_settings
from src.common.db import get_db_connection
from src.processing.spark_session import (
    get_jdbc_properties,
    get_jdbc_url,
    get_spark_session,
)
from src.quality.rules import QualitySummary, evaluate_quality


logger = logging.getLogger(__name__)

# Esquema explícito para parsear el GeoJSON de la API del USGS
GEOJSON_FEATURE_SCHEMA = StructType([
    StructField("id", StringType(), True),
    StructField("properties", StructType([
        StructField("mag", DoubleType(), True),
        StructField("place", StringType(), True),
        StructField("time", LongType(), True),
        StructField("updated", LongType(), True),
        StructField("tsunami", IntegerType(), True),
        StructField("code", StringType(), True),
    ]), True),
    StructField("geometry", StructType([
        StructField("coordinates", ArrayType(DoubleType()), True),
    ]), True),
])


def extract_region_column():
    """Regla determinista para extraer la región a partir del campo de lugar ('place').

    1. Si place es nulo -> 'Unknown'.
    2. Si contiene coma (ej. '35 km SSE of Whites City, New Mexico') -> toma la porción tras la última coma ('New Mexico').
    3. Si no tiene coma pero contiene ' of ' (ej. 'off the coast of Oregon') -> toma la porción tras ' of ' ('Oregon').
    4. En cualquier otro caso -> usa el texto completo limpio de espacios.
    """
    return (
        when(col("place").isNull(), "Unknown")
        .when(col("place").contains(","), trim(element_at(split(col("place"), ","), -1)))
        .when(col("place").contains(" of "), trim(element_at(split(col("place"), " of "), -1)))
        .otherwise(trim(col("place")))
    )


def parse_and_normalize_bronze(df: DataFrame) -> DataFrame:
    """Parsea el GeoJSON de payload_text y normaliza columnas y tipos a la estructura Silver."""
    parsed = df.withColumn("parsed", from_json(col("payload_text"), GEOJSON_FEATURE_SCHEMA))

    normalized = parsed.select(
        coalesce(col("parsed.id"), col("parsed.properties.code"), col("event_id")).alias("event_id"),
        spark_round(col("parsed.properties.mag"), 2).alias("magnitude"),
        col("parsed.properties.place").alias("place"),
        to_timestamp(from_unixtime(col("parsed.properties.time") / 1000.0)).alias("time_utc"),
        to_timestamp(from_unixtime(col("parsed.properties.updated") / 1000.0)).alias("updated_at_utc"),
        col("parsed.geometry.coordinates")[0].alias("longitude"),
        col("parsed.geometry.coordinates")[1].alias("latitude"),
        spark_round(col("parsed.geometry.coordinates")[2], 2).alias("depth_km"),
        when(col("parsed.properties.tsunami") == 1, True).otherwise(False).alias("tsunami_alert"),
        col("ingested_at"),
        col("source_updated_at"),
    )

    # Derivación de la región a partir del lugar
    return normalized.withColumn("region", extract_region_column())


def deduplicate_events(df: DataFrame) -> DataFrame:
    """Deduplica eventos por event_id conservando la versión más reciente según updated_at_utc."""
    window_spec = Window.partitionBy("event_id").orderBy(
        col("updated_at_utc").desc(),
        col("source_updated_at").desc(),
    )
    return (
        df.withColumn("row_num", row_number().over(window_spec))
        .filter(col("row_num") == 1)
        .drop("row_num")
    )


def read_pending_bronze(spark: SparkSession, batch_id: Optional[uuid.UUID] = None) -> DataFrame:
    """Lee lotes desde bronze.earthquakes proyectando payload como texto para JDBC."""
    jdbc_url = get_jdbc_url()
    jdbc_props = get_jdbc_properties("pipeline")

    if batch_id:
        query = f"(SELECT id, event_id, batch_id, ingested_at, source_updated_at, payload::text AS payload_text FROM bronze.earthquakes WHERE batch_id = '{batch_id}') AS bronze_query"
    else:
        # Lectura de los registros más recientes aún no procesados a Silver
        query = """
        (
            SELECT b.id, b.event_id, b.batch_id, b.ingested_at, b.source_updated_at, b.payload::text AS payload_text
            FROM bronze.earthquakes b
            LEFT JOIN silver.earthquakes s ON b.event_id = s.event_id AND b.source_updated_at <= s.updated_at_utc
            WHERE s.event_id IS NULL
        ) AS bronze_pending
        """

    return spark.read.jdbc(
        url=jdbc_url,
        table=query,
        properties=jdbc_props,
    )


def write_staging_silver(df: DataFrame, staging_table: str = "silver._staging_earthquakes") -> None:
    """Vuelca el DataFrame de registros válidos en la tabla temporal de staging por JDBC."""
    jdbc_url = get_jdbc_url()
    jdbc_props = get_jdbc_properties("pipeline")

    # Columnas ordenadas según la definición de silver.earthquakes
    export_df = df.select(
        "event_id",
        "magnitude",
        "place",
        "region",
        "time_utc",
        "updated_at_utc",
        "longitude",
        "latitude",
        "depth_km",
        "tsunami_alert",
        "ingested_at",
    )

    export_df.write.jdbc(
        url=jdbc_url,
        table=staging_table,
        mode="overwrite",
        properties=jdbc_props,
    )


def execute_silver_upsert(conn: Connection, staging_table: str = "silver._staging_earthquakes") -> int:
    """Traspasa los registros del staging a la tabla final de Silver de forma atómica e idempotente."""
    upsert_sql = f"""
    INSERT INTO silver.earthquakes (
        event_id,
        magnitude,
        place,
        region,
        time_utc,
        updated_at_utc,
        longitude,
        latitude,
        depth_km,
        tsunami_alert,
        ingested_at,
        created_at,
        updated_at
    )
    SELECT
        event_id,
        magnitude,
        place,
        region,
        time_utc,
        updated_at_utc,
        longitude,
        latitude,
        depth_km,
        tsunami_alert,
        ingested_at,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    FROM {staging_table}
    ON CONFLICT (event_id) DO UPDATE SET
        magnitude = EXCLUDED.magnitude,
        place = EXCLUDED.place,
        region = EXCLUDED.region,
        time_utc = EXCLUDED.time_utc,
        updated_at_utc = EXCLUDED.updated_at_utc,
        longitude = EXCLUDED.longitude,
        latitude = EXCLUDED.latitude,
        depth_km = EXCLUDED.depth_km,
        tsunami_alert = EXCLUDED.tsunami_alert,
        ingested_at = EXCLUDED.ingested_at,
        updated_at = CURRENT_TIMESTAMP
    WHERE EXCLUDED.updated_at_utc >= silver.earthquakes.updated_at_utc;
    """
    with conn.cursor() as cur:
        cur.execute(upsert_sql)
        row_count = cur.rowcount
    return row_count


def persist_quality_metrics(
    conn: Connection,
    batch_id: uuid.UUID,
    summary: QualitySummary,
) -> None:
    """Registra en metrics.data_quality el resumen cuantitativo del lote evaluado."""
    insert_sql = """
    INSERT INTO metrics.data_quality (
        batch_id,
        evaluated_at,
        total_records,
        valid_records,
        invalid_records,
        quality_score,
        failed_rules
    ) VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s);
    """
    with conn.cursor() as cur:
        cur.execute(
            insert_sql,
            (
                batch_id,
                summary.total_records,
                summary.valid_records,
                summary.invalid_records,
                summary.quality_score,
                json.dumps(summary.failed_rules),
            ),
        )


def run_bronze_to_silver(batch_id: Optional[uuid.UUID] = None) -> dict[str, Any]:
    """Flujo principal Bronze → Silver con PySpark."""
    eval_batch_id = batch_id or uuid.uuid4()
    logger.info("Iniciando transformación Spark Bronze -> Silver para lote: %s", eval_batch_id)

    with get_spark_session(app_name="BronzeToSilverTransformation") as spark:
        bronze_df = read_pending_bronze(spark, batch_id)
        raw_count = bronze_df.count()

        if raw_count == 0:
            logger.info("No se encontraron registros pendientes en Bronze.")
            return {
                "batch_id": str(eval_batch_id),
                "total_records": 0,
                "valid_records": 0,
                "invalid_records": 0,
                "quality_score": 100.0,
                "status": "NO_DATA",
            }

        # 1. Normalización y tipado
        normalized_df = parse_and_normalize_bronze(bronze_df)

        # 2. Evaluación de reglas de calidad (descarte en memoria de inválidos)
        valid_df, _, quality_summary = evaluate_quality(normalized_df)

        # 3. Deduplicación por clave primaria (conservando la versión más reciente)
        deduped_valid_df = deduplicate_events(valid_df)

        # 4. Escritura en staging por JDBC
        write_staging_silver(deduped_valid_df)

        # 5. Upsert atómico y persistencia de métricas en PostgreSQL
        with get_db_connection("pipeline") as conn:
            upserted = execute_silver_upsert(conn)
            persist_quality_metrics(conn, eval_batch_id, quality_summary)
            conn.commit()

        logger.info(
            "Transformación Bronze -> Silver finalizada. Total: %d, Válidos: %d, Descartados: %d, Calidad: %.2f%%, Upserted: %d",
            quality_summary.total_records,
            quality_summary.valid_records,
            quality_summary.invalid_records,
            quality_summary.quality_score,
            upserted,
        )

        return {
            "batch_id": str(eval_batch_id),
            "total_records": quality_summary.total_records,
            "valid_records": quality_summary.valid_records,
            "invalid_records": quality_summary.invalid_records,
            "quality_score": quality_summary.quality_score,
            "failed_rules": quality_summary.failed_rules,
            "upserted_to_silver": upserted,
            "status": "SUCCESS",
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_bronze_to_silver()
    print("Resultado:", result)
