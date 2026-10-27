"""Punto de entrada principal para la aplicación FastAPI.

Expone endpoints REST y el canal SSE para el consumo de la capa Gold por parte del frontend.
"""
from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers.events import router as events_router
from src.api.routers.metrics import router as metrics_router
from src.api.routers.operations import router as operations_router
from src.api.schemas import HealthResponse
from src.api.services import AnalyticsService
from src.common.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="Plataforma de Análisis Sísmico - API Gold",
    description="Backend analítico sobre PostgreSQL (Gold/Ops) con soporte para Server-Sent Events (SSE).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración de CORS para el frontend React
origins = settings.api.cors_origins or ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if "*" not in origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Manejador Global de Errores (Seguridad: no filtra credenciales ni trazas)
# ==============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Captura excepciones no controladas evitando exponer detalles sensibles de la base de datos."""
    logger.exception("Error no controlado atendiendo solicitud %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Ocurrió un error interno procesando la solicitud analítica.",
            "path": request.url.path,
        },
    )


# ==============================================================================
# Endpoint de Salud (Healthcheck para Docker y observabilidad)
# ==============================================================================
@app.get("/api/v1/health", response_model=HealthResponse, tags=["Salud"])
@app.get("/health", response_model=HealthResponse, include_in_schema=False)
def healthcheck() -> HealthResponse:
    """Verifica el estado del servicio y la conectividad a la base de datos con api_reader."""
    return AnalyticsService.check_health()


# ==============================================================================
# Inclusión de Enrutadores con prefijo /api/v1
# ==============================================================================
app.include_router(events_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(operations_router, prefix="/api/v1")

# Alias para facilitar compatibilidad /api
app.include_router(events_router, prefix="/api", include_in_schema=False)
app.include_router(metrics_router, prefix="/api", include_in_schema=False)
app.include_router(operations_router, prefix="/api", include_in_schema=False)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirección informativa inicial."""
    return {
        "service": "Plataforma de Análisis Sísmico API",
        "documentation": "/docs",
        "health": "/api/v1/health",
        "version": "1.0.0",
    }
