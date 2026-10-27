"""Procesamiento de datos de Silver a Gold utilizando Apache Spark (PySpark)."""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional
import uuid
from psycopg import Connection
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    current_timestamp,
    date_trunc,
    expr,
    max as spark_max,
    round as spark_round,
    when,
)
from src.common.db import get_db_connection
from src.processing.spark_session import (
    get_jdbc_properties,
    get_jdbc_url,
    get_spark_session,
)


logger = logging.getLogger(__name__)


def build_gold_earthquakes(silver_df: DataFrame) -> DataFrame:
    """Prepara los eventos normalizados para consulta y visualización en el mapa."""
    return silver_df.select(
        "event_id",
        "magnitude",
        "place",
        "region",
        "time_utc",
        "longitude",
        "latitude",
        "depth_km",
        "tsunami_alert",
        "updated_at_utc",
    )


def build_hourly_regional_stats(silver_df: DataFrame) -> DataFrame:
    """Calcula agregaciones por hora y región. Sirve de base para la detección de anomalías."""
    return (
        silver_df.withColumn("hour_bucket", date_trunc("hour", col("time_utc")))
        .groupBy("region", "hour_bucket")
        .agg(
            count("*").alias("event_count"),
            spark_round(avg("magnitude"), 2).alias("avg_magnitude"),
            spark_round(spark_max("magnitude"), 2).alias("max_magnitude"),
        )
    )


def build_magnitude_distribution(silver_df: DataFrame) -> DataFrame:
    """Calcula la distribución agregada de eventos en rangos estándar de magnitud."""
    bracket_expr = (
        when(col("magnitude") < 3.0, "2.5 - 2.9")
        .when((col("magnitude") >= 3.0) & (col("magnitude") < 4.0), "3.0 - 3.9")
        .when((col("magnitude") >= 4.0) & (col("magnitude") < 5.0), "4.0 - 4.9")
        .when((col("magnitude") >= 5.0) & (col("magnitude") < 6.0), "5.0 - 5.9")
        .otherwise("6.0+")
    )
    return (
        silver_df.withColumn("magnitude_bracket", bracket_expr)
        .groupBy("magnitude_bracket")
        .agg(count("*").alias("event_count"))
    )


def build_regional_ranking_24h(
    silver_df: DataFrame,
    reference_time: Optional[datetime] = None,
) -> DataFrame:
    """Calcula el ranking de regiones con mayor actividad sísmica en las últimas 24 horas."""
    if reference_time:
        cutoff = reference_time - timedelta(hours=24)
        filtered = silver_df.filter(col("time_utc") >= cutoff)
    else:
        filtered = silver_df.filter(col("time_utc") >= (current_timestamp() - expr("INTERVAL 24 HOURS")))

    return (
        filtered.groupBy("region")
        .agg(
            count("*").alias("total_events_24h"),
            spark_round(spark_max("magnitude"), 2).alias("max_magnitude_24h"),
        )
        .orderBy(col("total_events_24h").desc(), col("max_magnitude_24h").desc())
    )


def read_silver_events(spark: SparkSession) -> DataFrame:
    """Lee todos los eventos normalizados y validados desde silver.earthquakes vía JDBC."""
    jdbc_url = get_jdbc_url()
    jdbc_props = get_jdbc_properties("pipeline")

    return spark.read.jdbc(
        url=jdbc_url,
        table="silver.earthquakes",
        properties=jdbc_props,
    )


def write_gold_staging(df: DataFrame, staging_table: str) -> None:
    """Escribe un DataFrame transformado en una tabla volátil de staging de Gold vía JDBC."""
    jdbc_url = get_jdbc_url()
    jdbc_props = get_jdbc_properties("pipeline")

    df.write.jdbc(
        url=jdbc_url,
        table=staging_table,
        mode="overwrite",
        properties=jdbc_props,
    )


def execute_gold_upsert(conn: Connection) -> dict[str, int]:
    """Aplica sentencias SQL atómicas para trasladar datos desde las tablas de staging a Gold."""
    results = {}

    with conn.cursor() as cur:
        # 1. Upsert en gold.earthquakes
        cur.execute("""
            INSERT INTO gold.earthquakes (
                event_id, magnitude, place, region, time_utc,
                longitude, latitude, depth_km, tsunami_alert, updated_at_utc
            )
            SELECT
                event_id, magnitude, place, region, time_utc,
                longitude, latitude, depth_km, tsunami_alert, updated_at_utc
            FROM gold._staging_earthquakes
            ON CONFLICT (event_id) DO UPDATE SET
                magnitude = EXCLUDED.magnitude,
                place = EXCLUDED.place,
                region = EXCLUDED.region,
                time_utc = EXCLUDED.time_utc,
                longitude = EXCLUDED.longitude,
                latitude = EXCLUDED.latitude,
                depth_km = EXCLUDED.depth_km,
                tsunami_alert = EXCLUDED.tsunami_alert,
                updated_at_utc = EXCLUDED.updated_at_utc
            WHERE EXCLUDED.updated_at_utc >= gold.earthquakes.updated_at_utc;
        """)
        results["earthquakes_upserted"] = cur.rowcount

        # 2. Upsert en gold.hourly_regional_stats
        cur.execute("""
            INSERT INTO gold.hourly_regional_stats (
                region, hour_bucket, event_count, avg_magnitude, max_magnitude, updated_at
            )
            SELECT
                region, hour_bucket, event_count, avg_magnitude, max_magnitude, CURRENT_TIMESTAMP
            FROM gold._staging_hourly_regional_stats
            ON CONFLICT (region, hour_bucket) DO UPDATE SET
                event_count = EXCLUDED.event_count,
                avg_magnitude = EXCLUDED.avg_magnitude,
                max_magnitude = EXCLUDED.max_magnitude,
                updated_at = CURRENT_TIMESTAMP;
        """)
        results["hourly_stats_upserted"] = cur.rowcount

        # 3. Upsert en gold.magnitude_distribution
        cur.execute("""
            INSERT INTO gold.magnitude_distribution (
                magnitude_bracket, event_count, updated_at
            )
            SELECT
                magnitude_bracket, event_count, CURRENT_TIMESTAMP
            FROM gold._staging_magnitude_distribution
            ON CONFLICT (magnitude_bracket) DO UPDATE SET
                event_count = EXCLUDED.event_count,
                updated_at = CURRENT_TIMESTAMP;
        """)
        results["magnitude_distribution_upserted"] = cur.rowcount

        # 4. Refresco atómico de gold.regional_ranking (ventana móvil 24h)
        cur.execute("TRUNCATE TABLE gold.regional_ranking;")
        cur.execute("""
            INSERT INTO gold.regional_ranking (
                region, total_events_24h, max_magnitude_24h, updated_at
            )
            SELECT
                region, total_events_24h, max_magnitude_24h, CURRENT_TIMESTAMP
            FROM gold._staging_regional_ranking;
        """)
        results["regional_ranking_refreshed"] = cur.rowcount

    return results


def run_silver_to_gold(batch_id: Optional[uuid.UUID] = None) -> dict[str, Any]:
    """Ejecuta el pipeline completo de transformaciones analíticas Silver -> Gold."""
    eval_batch_id = batch_id or uuid.uuid4()
    logger.info("Iniciando transformaciones Spark Silver -> Gold (Batch: %s)", eval_batch_id)

    with get_spark_session(app_name="SilverToGoldTransformation") as spark:
        silver_df = read_silver_events(spark)
        count_silver = silver_df.count()

        if count_silver == 0:
            logger.info("No se encontraron registros en Silver para procesar a Gold.")
            return {
                "batch_id": str(eval_batch_id),
                "status": "NO_DATA",
                "silver_records": 0,
            }

        # 1. Transformaciones PySpark
        gold_events_df = build_gold_earthquakes(silver_df)
        hourly_stats_df = build_hourly_regional_stats(silver_df)
        mag_dist_df = build_magnitude_distribution(silver_df)
        regional_ranking_df = build_regional_ranking_24h(silver_df)

        # 2. Escritura masiva en tablas de staging vía JDBC
        write_gold_staging(gold_events_df, "gold._staging_earthquakes")
        write_gold_staging(hourly_stats_df, "gold._staging_hourly_regional_stats")
        write_gold_staging(mag_dist_df, "gold._staging_magnitude_distribution")
        write_gold_staging(regional_ranking_df, "gold._staging_regional_ranking")

        # 3. Traslado atómico e idempotente a las tablas finales de Gold
        with get_db_connection("pipeline") as conn:
            upsert_results = execute_gold_upsert(conn)
            conn.commit()

        logger.info("Transformación Silver -> Gold completada con éxito: %s", upsert_results)

        return {
            "batch_id": str(eval_batch_id),
            "status": "SUCCESS",
            "silver_records": count_silver,
            "upsert_results": upsert_results,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    res = run_silver_to_gold()
    print("Resultado Silver -> Gold:", res)
