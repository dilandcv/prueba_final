"""Endpoints para métricas analíticas e indicadores consolidados."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from src.api.schemas import (
    GeneralIndicatorsResponse,
    MagnitudeDistributionItem,
    QualitySummaryResponse,
    RegionalRankingItem,
)
from src.api.services import AnalyticsService


router = APIRouter(prefix="/metrics", tags=["Métricas e Indicadores"])


@router.get("/indicators", response_model=GeneralIndicatorsResponse)
def get_general_indicators(
    start_date: Optional[datetime] = Query(None, description="Fecha inicio UTC"),
    end_date: Optional[datetime] = Query(None, description="Fecha fin UTC"),
    min_magnitude: Optional[float] = Query(None, ge=-2.0, le=10.0, description="Magnitud mínima"),
    region: Optional[str] = Query(None, max_length=100, description="Región geográfica"),
) -> GeneralIndicatorsResponse:
    """Retorna indicadores agregados: conteo, magnitud máx/promedio, tsunamis y calidad."""
    return AnalyticsService.get_general_indicators(
        start_date=start_date,
        end_date=end_date,
        min_magnitude=min_magnitude,
        region=region,
    )


@router.get("/magnitude-distribution", response_model=list[MagnitudeDistributionItem])
def get_magnitude_distribution(
    start_date: Optional[datetime] = Query(None, description="Fecha inicio UTC"),
    end_date: Optional[datetime] = Query(None, description="Fecha fin UTC"),
    region: Optional[str] = Query(None, max_length=100, description="Región geográfica"),
) -> list[MagnitudeDistributionItem]:
    """Retorna la distribución de sismos agrupados por intervalos de magnitud estándar."""
    return AnalyticsService.get_magnitude_distribution(
        start_date=start_date,
        end_date=end_date,
        region=region,
    )


@router.get("/regional-ranking", response_model=list[RegionalRankingItem])
def get_regional_ranking(
    limit: int = Query(10, ge=1, le=50, description="Cantidad máxima de regiones en el ranking"),
) -> list[RegionalRankingItem]:
    """Retorna el ranking de las regiones con mayor frecuencia sísmica en las últimas 24 horas."""
    return AnalyticsService.get_regional_ranking(limit=limit)


@router.get("/quality", response_model=QualitySummaryResponse)
def get_quality_metrics() -> QualitySummaryResponse:
    """Retorna el último puntaje y desglose de reglas de calidad evaluadas por PySpark."""
    return AnalyticsService.get_quality_summary()
