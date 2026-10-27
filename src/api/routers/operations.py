"""Endpoints operativos: calidad, anomalías, reportes de IA y estado del pipeline."""
from fastapi import APIRouter, Query

from src.ai.chat_service import process_chat_message
from src.api.schemas import (
    AIReportItem,
    AnomalyAlertItem,
    ChatRequest,
    ChatResponse,
    PipelineStatusResponse,
    QualitySummaryResponse,
)
from src.api.services import AnalyticsService


router = APIRouter(tags=["Operaciones y Gobernanza"])


@router.get("/quality/summary", response_model=QualitySummaryResponse)
def get_quality_summary() -> QualitySummaryResponse:
    """Retorna el puntaje de calidad y estado del lote más reciente."""
    return AnalyticsService.get_quality_summary()


@router.get("/alerts/anomalies", response_model=list[AnomalyAlertItem])
def get_anomaly_alerts(
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de alertas"),
) -> list[AnomalyAlertItem]:
    """Retorna alertas de anomalías estadísticas detectadas por el pipeline analítico."""
    return AnalyticsService.get_anomaly_alerts(limit=limit)


@router.get("/ai/reports", response_model=list[AIReportItem])
def get_ai_reports(
    limit: int = Query(10, ge=1, le=50, description="Cantidad máxima de reportes"),
) -> list[AIReportItem]:
    """Retorna los reportes narrativos y auditorías de IA local generadas."""
    return AnalyticsService.get_ai_reports(limit=limit)


@router.post("/ai/chat", response_model=ChatResponse)
def chat_with_ai_agent(payload: ChatRequest) -> ChatResponse:
    """Interacción conversacional con el agente de IA local sobre los datos sísmicos verificados."""
    return process_chat_message(message=payload.message, history=payload.history)



@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def get_pipeline_status() -> PipelineStatusResponse:
    """Retorna el estado operativo actual de las corridas de Airflow y disponibilidad de datos."""
    return AnalyticsService.get_pipeline_status()
