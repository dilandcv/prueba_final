"""Modelos Pydantic para validación de entrada y serialización de respuestas de la API."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# Parámetros de Filtro Comunes
# ==============================================================================
class FilterParams(BaseModel):
    """Parámetros de consulta y filtrado admitidos por los endpoints analíticos."""
    start_date: Optional[datetime] = Field(None, description="Fecha y hora de inicio UTC")
    end_date: Optional[datetime] = Field(None, description="Fecha y hora de fin UTC")
    min_magnitude: Optional[float] = Field(None, ge=-2.0, le=10.0, description="Magnitud mínima (Richter)")
    region: Optional[str] = Field(None, max_length=100, description="Nombre de la región geográfica")
    limit: int = Field(500, ge=1, le=2000, description="Límite de registros retornados")


# ==============================================================================
# Respuestas de Indicadores y Métricas
# ==============================================================================
class GeneralIndicatorsResponse(BaseModel):
    """Resumen cuantitativo global de sismicidad y salud de datos."""
    events_count: int = Field(..., description="Total de sismos en el periodo consultado")
    max_magnitude: Optional[float] = Field(None, description="Magnitud máxima registrada")
    avg_magnitude: Optional[float] = Field(None, description="Magnitud promedio registrada")
    tsunami_alerts_count: int = Field(..., description="Total de eventos con alerta de tsunami")
    quality_score: float = Field(..., description="Puntaje de calidad del último lote (0.0 a 100.0)")
    last_update: Optional[datetime] = Field(None, description="Marca temporal del último procesamiento exitoso")


class TimeSeriesPoint(BaseModel):
    """Punto en la serie temporal de conteo y magnitudes horarias."""
    hour_bucket: datetime = Field(..., description="Inicio de la ventana horaria UTC")
    total_events: int = Field(..., description="Conteo de eventos en la hora")
    avg_magnitude: Optional[float] = Field(None, description="Magnitud promedio en la hora")
    max_magnitude: Optional[float] = Field(None, description="Magnitud máxima en la hora")


class MagnitudeDistributionItem(BaseModel):
    """Conteo de sismos dentro de un rango de magnitud."""
    magnitude_bracket: str = Field(..., description="Rango de magnitud (e.g. '4.0 - 4.9')")
    event_count: int = Field(..., description="Total de eventos dentro del rango")


class RegionalRankingItem(BaseModel):
    """Posición en el ranking de regiones con mayor actividad sísmica reciente."""
    region: str = Field(..., description="Nombre de la región")
    total_events_24h: int = Field(..., description="Total de eventos en las últimas 24 horas")
    max_magnitude_24h: Optional[float] = Field(None, description="Magnitud máxima registrada en 24h")
    rank_position: int = Field(..., description="Posición en el ranking (1 = mayor actividad)")


# ==============================================================================
# Eventos para Mapa Geográfico
# ==============================================================================
class MapEventItem(BaseModel):
    """Detalle geográfico y técnico de un evento sísmico para renderizado en mapa."""
    event_id: str = Field(..., description="Identificador único del USGS")
    magnitude: float = Field(..., description="Magnitud del sismo")
    place: str = Field(..., description="Descripción textual del lugar")
    region: str = Field(..., description="Región normalizada")
    time_utc: datetime = Field(..., description="Fecha y hora de ocurrencia UTC")
    latitude: float = Field(..., description="Latitud (-90.0 a 90.0)")
    longitude: float = Field(..., description="Longitud (-180.0 a 180.0)")
    depth_km: Optional[float] = Field(None, description="Profundidad focal en kilómetros")
    tsunami_alert: bool = Field(False, description="Bandera de alerta de tsunami")


# ==============================================================================
# Calidad, Alertas y Operaciones
# ==============================================================================
class QualitySummaryResponse(BaseModel):
    """Métricas de calidad de datos del último lote evaluado."""
    quality_score: float = Field(..., description="Puntaje de calidad global (0.0 a 100.0)")
    total_records: int = Field(..., description="Total de registros evaluados")
    valid_records: int = Field(..., description="Total de registros que cumplieron todas las reglas")
    invalid_records: int = Field(..., description="Total de registros descartados")
    failed_rules: dict[str, int] = Field(default_factory=dict, description="Desglose agregado de reglas infringidas")
    evaluated_at: Optional[datetime] = Field(None, description="Fecha de evaluación UTC")


class AnomalyAlertItem(BaseModel):
    """Alerta de anomalía estadística detectada por Z-Score."""
    id: int = Field(..., description="Identificador de la alerta")
    detected_at: datetime = Field(..., description="Fecha de detección UTC")
    region: str = Field(..., description="Región de la anomalía")
    hour_bucket: datetime = Field(..., description="Ventana horaria evaluada")
    event_count: int = Field(..., description="Eventos observados")
    z_score: float = Field(..., description="Puntaje Z estadístico")
    threshold: float = Field(..., description="Umbral de detección aplicado")
    narrative_explanation: str = Field(..., description="Explicación narrativa generada")


class AIReportItem(BaseModel):
    """Registro de ejecución y reporte generado por el módulo de IA."""
    id: int = Field(..., description="Identificador de la ejecución")
    executed_at: datetime = Field(..., description="Fecha de ejecución UTC")
    automation_type: str = Field(..., description="Tipo de automatización (e.g. 'ANOMALY_EXPLANATION')")
    model_name: str = Field(..., description="Nombre del modelo local utilizado")
    status: str = Field(..., description="Estado de la ejecución (SUCCESS, FALLBACK, ERROR)")
    used_fallback: bool = Field(False, description="Indica si se recurrió a generación determinista")


class PipelineStatusResponse(BaseModel):
    """Estado operativo de la orquestación y disponibilidad de datos."""
    status: str = Field(..., description="Estado general ('HEALTHY', 'DEGRADED')")
    last_run_status: Optional[str] = Field(None, description="Estado de la última corrida en Airflow")
    last_batch_id: Optional[str] = Field(None, description="Identificador del último lote")
    last_available_at: Optional[datetime] = Field(None, description="Fecha del último lote disponible")
    records_processed: int = Field(0, description="Registros procesados en el último ciclo")


class HealthResponse(BaseModel):
    """Respuesta de salud del servicio backend."""
    status: str = Field("UP", description="Estado del servidor")
    database: str = Field(..., description="Estado de la conexión a PostgreSQL")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Hora de chequeo")


# ==============================================================================
# Chatbot y Asistente Conversacional
# ==============================================================================
class ChatMessageItem(BaseModel):
    """Mensaje individual en el historial de conversación."""
    role: str = Field(..., description="Rol del remitente ('user' o 'assistant')")
    content: str = Field(..., min_length=1, description="Contenido textual del mensaje")


class ChatRequest(BaseModel):
    """Petición conversacional enviada al asistente de IA."""
    message: str = Field(..., min_length=1, max_length=2000, description="Pregunta del usuario")
    history: list[ChatMessageItem] = Field(default_factory=list, description="Historial previo de mensajes")


class ChatResponse(BaseModel):
    """Respuesta generada por el agente de IA para el chatbot."""
    response: str = Field(..., description="Respuesta en lenguaje natural fundamentada en datos")
    model_name: str = Field(..., description="Nombre del modelo de inferencia o fallback")
    used_fallback: bool = Field(False, description="Indica si se recurrió al motor determinista")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Fecha y hora UTC de la respuesta")

