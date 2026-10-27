"""Reglas de calidad de datos para validación y filtrado de eventos sísmicos en Spark."""
from typing import NamedTuple
from pyspark.sql import Column, DataFrame
from pyspark.sql.functions import col, current_timestamp, round as spark_round, sum as spark_sum, when


class QualitySummary(NamedTuple):
    """Métricas consolidadas de calidad para un lote evaluado."""
    total_records: int
    valid_records: int
    invalid_records: int
    quality_score: float
    failed_rules: dict[str, int]


def get_quality_conditions() -> dict[str, Column]:
    """Devuelve las condiciones booleanas de calidad que debe cumplir cada registro."""
    return {
        # 1. Identificador obligatorio y no vacío
        "rule_id_not_null": col("event_id").isNotNull() & (col("event_id") != ""),
        # 2. Magnitud numérica dentro de rango físico admisible (-2.0 a 10.0)
        "rule_magnitude_valid": col("magnitude").isNotNull() & (col("magnitude") >= -2.0) & (col("magnitude") <= 10.0),
        # 3. Fecha válida y no en el futuro
        "rule_time_valid": col("time_utc").isNotNull() & (col("time_utc") <= current_timestamp()),
        # 4. Coordenadas dentro de límites geográficos (-90..90 lat, -180..180 lon)
        "rule_coordinates_valid": (
            col("latitude").isNotNull()
            & (col("latitude") >= -90.0)
            & (col("latitude") <= 90.0)
            & col("longitude").isNotNull()
            & (col("longitude") >= -180.0)
            & (col("longitude") <= 180.0)
        ),
        # 5. Indicador de tsunami definido
        "rule_tsunami_valid": col("tsunami_alert").isNotNull(),
    }


def evaluate_quality(df: DataFrame) -> tuple[DataFrame, DataFrame, QualitySummary]:
    """Evalúa las reglas de calidad en memoria sin persistir registros inválidos.

    Retorna:
    - valid_df: DataFrame únicamente con registros que cumplen el 100% de las reglas.
    - invalid_df: DataFrame en memoria con registros descartados (para inspección o auditoría).
    - summary: Resumen cuantitativo y contadores agregados por regla infringida.
    """
    conditions = get_quality_conditions()

    # Marcamos banderas de fallo por cada regla (1 si falla, 0 si cumple)
    evaluated_df = df
    rule_flags = []
    is_valid_expr = None

    for rule_name, condition in conditions.items():
        flag_col = f"failed_{rule_name}"
        rule_flags.append(flag_col)
        evaluated_df = evaluated_df.withColumn(flag_col, when(~condition, 1).otherwise(0))

        if is_valid_expr is None:
            is_valid_expr = condition
        else:
            is_valid_expr = is_valid_expr & condition

    evaluated_df = evaluated_df.withColumn("is_valid", is_valid_expr)

    # Cálculo agregado de métricas en una única pasada
    agg_exprs = [spark_sum(flag_col).alias(flag_col) for flag_col in rule_flags]
    agg_row = evaluated_df.agg(*agg_exprs).first()

    failed_counts = {}
    for rule_name in conditions.keys():
        flag_col = f"failed_{rule_name}"
        count_val = agg_row[flag_col] if agg_row and agg_row[flag_col] is not None else 0
        failed_counts[rule_name] = int(count_val)

    total_records = evaluated_df.count()
    valid_df = evaluated_df.filter(col("is_valid")).drop(*rule_flags, "is_valid")
    invalid_df = evaluated_df.filter(~col("is_valid")).drop(*rule_flags, "is_valid")

    valid_count = valid_df.count()
    invalid_count = total_records - valid_count

    quality_score = (
        round((valid_count / total_records) * 100.0, 2)
        if total_records > 0
        else 100.0
    )

    summary = QualitySummary(
        total_records=total_records,
        valid_records=valid_count,
        invalid_records=invalid_count,
        quality_score=quality_score,
        failed_rules=failed_counts,
    )

    return valid_df, invalid_df, summary
