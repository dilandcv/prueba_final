"""Catálogo estructurado de activos, etiquetas de gobierno y linaje para OpenMetadata."""
from typing import Any


CLASSIFICATIONS = [
    {
        "name": "Medallion",
        "description": "Capas arquitectónicas del almacén de datos (Bronze, Silver, Gold)",
        "tags": [
            {"name": "Bronze", "description": "Datos crudos inmutables append-only obtenidos directamente del USGS"},
            {"name": "Silver", "description": "Datos limpios, normalizados y validados por reglas de calidad de PySpark"},
            {"name": "Gold", "description": "Modelos dimensionales y métricas analíticas agregadas listas para consumo"},
        ],
    },
    {
        "name": "Governance",
        "description": "Etiquetas de gobierno de datos, observabilidad y operaciones",
        "tags": [
            {"name": "Quality", "description": "Control de calidad de datos, métricas y descarte en memoria"},
            {"name": "Operations", "description": "Auditoría de ejecuciones, alertas Z-score y trazabilidad de IA"},
        ],
    },
]

TABLES_CATALOG: list[dict[str, Any]] = [
    # Bronze Layer
    {
        "schema": "bronze",
        "name": "earthquakes",
        "description": "Almacén crudo inmutable de eventos sísmicos en formato append-only provenientes de la API del USGS.",
        "tags": ["Medallion.Bronze"],
        "columns": [
            {"name": "id", "type": "BIGINT", "description": "Identificador único autoincremental de auditoría"},
            {"name": "event_id", "type": "VARCHAR(50)", "description": "Identificador original del sismo en el USGS"},
            {"name": "batch_id", "type": "UUID", "description": "Identificador del lote de ingesta"},
            {"name": "ingested_at", "type": "TIMESTAMP", "description": "Marca de tiempo de inserción en Bronze"},
            {"name": "payload", "type": "JSONB", "description": "Feature GeoJSON completo sin procesar"},
        ],
    },
    # Silver Layer
    {
        "schema": "silver",
        "name": "earthquakes",
        "description": "Datos sísmicos validados, deduplicados y normalizados a tipos nativos mediante transformaciones PySpark.",
        "tags": ["Medallion.Silver"],
        "columns": [
            {"name": "event_id", "type": "VARCHAR(50)", "description": "Clave primaria única del sismo"},
            {"name": "batch_id", "type": "UUID", "description": "Lote que realizó la última actualización"},
            {"name": "magnitude", "type": "NUMERIC(4,2)", "description": "Magnitud en escala Richter/moms"},
            {"name": "place", "type": "VARCHAR(255)", "description": "Descripción geográfica del epicentro"},
            {"name": "time_utc", "type": "TIMESTAMP", "description": "Fecha y hora del sismo en UTC"},
            {"name": "updated_utc", "type": "TIMESTAMP", "description": "Última revisión reportada por USGS"},
            {"name": "latitude", "type": "NUMERIC(8,5)", "description": "Latitud en grados decimales (-90 a 90)"},
            {"name": "longitude", "type": "NUMERIC(8,5)", "description": "Longitud en grados decimales (-180 a 180)"},
            {"name": "depth_km", "type": "NUMERIC(6,2)", "description": "Profundidad focal en kilómetros"},
            {"name": "region", "type": "VARCHAR(100)", "description": "Región normalizada según regla sintáctica"},
            {"name": "tsunami_alert", "type": "BOOLEAN", "description": "Bandera de alerta de tsunami emitida"},
            {"name": "ingested_at", "type": "TIMESTAMP", "description": "Momento de procesamiento y upsert en Silver"},
        ],
    },
    # Gold Layer
    {
        "schema": "gold",
        "name": "earthquakes",
        "description": "Tabla analítica final de eventos sísmicos limpios preparada para consulta en mapa y agregaciones.",
        "tags": ["Medallion.Gold"],
        "columns": [
            {"name": "event_id", "type": "VARCHAR(50)", "description": "Clave primaria del sismo en Gold"},
            {"name": "magnitude", "type": "NUMERIC(4,2)", "description": "Magnitud normalizada"},
            {"name": "place", "type": "VARCHAR(255)", "description": "Lugar del epicentro"},
            {"name": "region", "type": "VARCHAR(100)", "description": "Región analítica"},
            {"name": "time_utc", "type": "TIMESTAMP", "description": "Fecha y hora UTC"},
            {"name": "latitude", "type": "NUMERIC(8,5)", "description": "Latitud"},
            {"name": "longitude", "type": "NUMERIC(8,5)", "description": "Longitud"},
            {"name": "depth_km", "type": "NUMERIC(6,2)", "description": "Profundidad en km"},
            {"name": "tsunami_alert", "type": "BOOLEAN", "description": "Alerta de tsunami"},
            {"name": "updated_at", "type": "TIMESTAMP", "description": "Última sincronización en Gold"},
        ],
    },
    {
        "schema": "gold",
        "name": "hourly_regional_stats",
        "description": "Conteos horarios y magnitudes por región para series temporales y detección de anomalías Z-Score.",
        "tags": ["Medallion.Gold"],
        "columns": [
            {"name": "region", "type": "VARCHAR(100)", "description": "Región geográfica"},
            {"name": "hour_bucket", "type": "TIMESTAMP", "description": "Intervalo horario truncado (UTC)"},
            {"name": "event_count", "type": "INT", "description": "Cantidad de sismos en el intervalo"},
            {"name": "avg_magnitude", "type": "NUMERIC(4,2)", "description": "Magnitud promedio de la hora"},
            {"name": "max_magnitude", "type": "NUMERIC(4,2)", "description": "Magnitud máxima de la hora"},
            {"name": "updated_at", "type": "TIMESTAMP", "description": "Momento de actualización"},
        ],
    },
    {
        "schema": "gold",
        "name": "magnitude_distribution",
        "description": "Distribución agregada de sismos según rangos estándar de intensidad sísmica.",
        "tags": ["Medallion.Gold"],
        "columns": [
            {"name": "magnitude_bracket", "type": "VARCHAR(20)", "description": "Rango de magnitud (ej: 3.0 - 3.9)"},
            {"name": "event_count", "type": "INT", "description": "Total de sismos en el rango"},
            {"name": "updated_at", "type": "TIMESTAMP", "description": "Momento de actualización"},
        ],
    },
    {
        "schema": "gold",
        "name": "regional_ranking",
        "description": "Ranking de las 10 regiones con mayor actividad sísmica registrada en las últimas 24 horas.",
        "tags": ["Medallion.Gold"],
        "columns": [
            {"name": "region", "type": "VARCHAR(100)", "description": "Región geográfica"},
            {"name": "total_events_24h", "type": "INT", "description": "Sismos acumulados en 24h"},
            {"name": "max_magnitude_24h", "type": "NUMERIC(4,2)", "description": "Magnitud máxima observada"},
            {"name": "rank_position", "type": "INT", "description": "Posición en el ranking"},
            {"name": "updated_at", "type": "TIMESTAMP", "description": "Momento de cálculo"},
        ],
    },
    # Metrics Layer
    {
        "schema": "metrics",
        "name": "data_quality",
        "description": "Auditoría de reglas de calidad evaluadas en PySpark durante el procesamiento de Bronze a Silver.",
        "tags": ["Governance.Quality"],
        "columns": [
            {"name": "id", "type": "BIGINT", "description": "Clave primaria de auditoría"},
            {"name": "batch_id", "type": "UUID", "description": "Identificador del lote evaluado"},
            {"name": "evaluated_at", "type": "TIMESTAMP", "description": "Momento de la evaluación"},
            {"name": "total_records", "type": "INT", "description": "Registros procesados"},
            {"name": "valid_records", "type": "INT", "description": "Registros que cumplieron el 100% de reglas"},
            {"name": "invalid_records", "type": "INT", "description": "Registros descartados en memoria"},
            {"name": "quality_score", "type": "NUMERIC(5,2)", "description": "Puntaje porcentual de calidad (0 a 100)"},
            {"name": "failed_rules", "type": "JSONB", "description": "Contadores por regla infringida"},
        ],
    },
    # Ops Layer
    {
        "schema": "ops",
        "name": "anomaly_alerts",
        "description": "Alertas estadísticas de frecuencia inusual basadas en Z-Score sobre conteos horarios de Gold.",
        "tags": ["Governance.Operations"],
        "columns": [
            {"name": "id", "type": "BIGINT", "description": "Identificador único de la alerta"},
            {"name": "detected_at", "type": "TIMESTAMP", "description": "Momento de detección"},
            {"name": "region", "type": "VARCHAR(100)", "description": "Región con frecuencia inusual"},
            {"name": "hour_bucket", "type": "TIMESTAMP", "description": "Hora con anomalía estadística"},
            {"name": "event_count", "type": "INT", "description": "Sismos observados en la hora"},
            {"name": "z_score", "type": "NUMERIC(5,2)", "description": "Puntuación Z-Score muestral"},
            {"name": "threshold", "type": "NUMERIC(5,2)", "description": "Umbral configurado"},
            {"name": "narrative_explanation", "type": "TEXT", "description": "Explicación en lenguaje natural (IA o fallback)"},
        ],
    },
]

LINEAGE_EDGES = [
    {
        "from": "postgres_seismic.seismic_platform.bronze.earthquakes",
        "to": "postgres_seismic.seismic_platform.silver.earthquakes",
        "description": "PySpark: parseo GeoJSON, validación de reglas de calidad y deduplicación upsert",
    },
    {
        "from": "postgres_seismic.seismic_platform.silver.earthquakes",
        "to": "postgres_seismic.seismic_platform.gold.earthquakes",
        "description": "PySpark: proyección dimensional para visualización y mapa analítico",
    },
    {
        "from": "postgres_seismic.seismic_platform.silver.earthquakes",
        "to": "postgres_seismic.seismic_platform.gold.hourly_regional_stats",
        "description": "PySpark: agregación de eventos y magnitudes agrupados por hora y región",
    },
    {
        "from": "postgres_seismic.seismic_platform.silver.earthquakes",
        "to": "postgres_seismic.seismic_platform.gold.magnitude_distribution",
        "description": "PySpark: conteos acumulados por rangos de magnitud Richter",
    },
    {
        "from": "postgres_seismic.seismic_platform.silver.earthquakes",
        "to": "postgres_seismic.seismic_platform.gold.regional_ranking",
        "description": "PySpark: ranking de las regiones más activas en las últimas 24 horas",
    },
    {
        "from": "postgres_seismic.seismic_platform.gold.hourly_regional_stats",
        "to": "postgres_seismic.seismic_platform.ops.anomaly_alerts",
        "description": "SQL Z-Score: detección estadística in-database y explicación con fallback IA",
    },
]
