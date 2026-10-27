"""Endpoints para consulta de eventos y flujo SSE de notificaciones en tiempo real."""
import asyncio
from datetime import datetime
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import MapEventItem, TimeSeriesPoint
from src.api.services import AnalyticsService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Eventos"])


@router.get("/map", response_model=list[MapEventItem])
def get_map_events(
    start_date: Optional[datetime] = Query(None, description="Fecha inicio UTC (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Fecha fin UTC (ISO 8601)"),
    min_magnitude: Optional[float] = Query(None, ge=-2.0, le=10.0, description="Magnitud mínima"),
    region: Optional[str] = Query(None, max_length=100, description="Región geográfica"),
    limit: int = Query(500, ge=1, le=2000, description="Límite máximo de eventos a desplegar"),
) -> list[MapEventItem]:
    """Retorna eventos sísmicos con coordenadas y atributos para visualización en mapa."""
    return AnalyticsService.get_map_events(
        start_date=start_date,
        end_date=end_date,
        min_magnitude=min_magnitude,
        region=region,
        limit=limit,
    )


@router.get("/timeseries", response_model=list[TimeSeriesPoint])
def get_events_timeseries(
    start_date: Optional[datetime] = Query(None, description="Fecha inicio UTC"),
    end_date: Optional[datetime] = Query(None, description="Fecha fin UTC"),
    min_magnitude: Optional[float] = Query(None, ge=-2.0, le=10.0, description="Magnitud mínima"),
    region: Optional[str] = Query(None, max_length=100, description="Región geográfica"),
) -> list[TimeSeriesPoint]:
    """Retorna la serie temporal de conteos y magnitudes promedio por hora UTC."""
    return AnalyticsService.get_timeseries(
        start_date=start_date,
        end_date=end_date,
        min_magnitude=min_magnitude,
        region=region,
    )


@router.get("/sse")
async def stream_data_availability_events(request: Request) -> EventSourceResponse:
    """Canal Server-Sent Events (SSE) para notificar al frontend cuando un lote queda disponible."""
    async def event_generator():
        # Evento de bienvenida con el estado inicial de conexión
        yield {
            "event": "connected",
            "data": json.dumps({"status": "CONNECTED"}),
        }

        # Inicializa rastreo con el último ID disponible
        latest_init = AnalyticsService.get_latest_availability()
        last_id = latest_init["id"] if latest_init else 0

        while True:
            if await request.is_disconnected():
                logger.info("Cliente desconectado del canal SSE.")
                break

            new_batch = AnalyticsService.get_latest_availability(after_id=last_id)
            if new_batch:
                last_id = new_batch["id"]
                logger.info("Notificando nuevo lote SSE disponible: %s", new_batch["batch_id"])
                yield {
                    "event": "data_update",
                    "data": json.dumps(new_batch),
                }

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator(), ping=15)
