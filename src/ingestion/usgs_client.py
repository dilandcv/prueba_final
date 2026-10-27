"""Cliente para la extracción de eventos sísmicos desde la API pública del USGS."""
from datetime import datetime, timezone
import logging
import time
from typing import Any, Optional
import requests
from requests.exceptions import HTTPError, RequestException, Timeout
from src.common.config import get_settings


logger = logging.getLogger(__name__)


class USGSAPIError(Exception):
    """Excepción base para errores en la interacción con la API del USGS."""
    pass


class USGSClient:
    """Cliente HTTP con reintentos y retroceso exponencial para la API del USGS."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        min_magnitude: Optional[float] = None,
        backoff_factor: float = 0.5,
    ) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.usgs.api_base_url
        self.timeout = timeout or settings.usgs.request_timeout_seconds
        self.max_retries = max_retries or settings.usgs.max_retries
        self.min_magnitude = min_magnitude if min_magnitude is not None else settings.usgs.min_magnitude
        self.backoff_factor = backoff_factor

    def build_query_params(
        self,
        starttime: Optional[datetime] = None,
        endtime: Optional[datetime] = None,
        updatedafter: Optional[datetime] = None,
        min_magnitude: Optional[float] = None,
        limit: int = 20000,
    ) -> dict[str, Any]:
        """Construye dinámicamente los parámetros de consulta según las especificaciones."""
        params: dict[str, Any] = {
            "format": "geojson",
            "minmagnitude": min_magnitude if min_magnitude is not None else self.min_magnitude,
            "orderby": "time-asc",
            "limit": limit,
        }

        if updatedafter:
            # Formato ISO 8601 en UTC para el parámetro updatedafter
            params["updatedafter"] = updatedafter.astimezone(timezone.utc).isoformat()
        else:
            if starttime:
                params["starttime"] = starttime.astimezone(timezone.utc).isoformat()
            if endtime:
                params["endtime"] = endtime.astimezone(timezone.utc).isoformat()

        return params

    def fetch_events(
        self,
        starttime: Optional[datetime] = None,
        endtime: Optional[datetime] = None,
        updatedafter: Optional[datetime] = None,
        min_magnitude: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """Realiza la petición HTTP a la API del USGS con reintentos y retroceso exponencial."""
        params = self.build_query_params(
            starttime=starttime,
            endtime=endtime,
            updatedafter=updatedafter,
            min_magnitude=min_magnitude,
        )

        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts < self.max_retries:
            attempts += 1
            try:
                logger.info(
                    "Consultando API USGS (intento %d/%d) con parámetros: %s",
                    attempts,
                    self.max_retries,
                    params,
                )
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout,
                    headers={"Accept": "application/json"},
                )

                # Si es un error 4xx o 5xx, levantamos excepción HTTP
                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError as err:
                    raise USGSAPIError("La respuesta de la API no contiene JSON válido") from err

                if not isinstance(payload, dict) or "features" not in payload:
                    raise USGSAPIError("Respuesta GeoJSON inválida: falta la clave 'features'")

                features = payload.get("features", [])
                logger.info("Extracción exitosa: %d eventos obtenidos del USGS.", len(features))
                return features

            except (Timeout, HTTPError, RequestException, USGSAPIError) as exc:
                last_exception = exc
                logger.warning(
                    "Fallo en intento %d/%d consultando USGS: %s",
                    attempts,
                    self.max_retries,
                    exc,
                )
                if attempts < self.max_retries:
                    # Espera con retroceso exponencial
                    sleep_time = self.backoff_factor * (2 ** (attempts - 1))
                    time.sleep(sleep_time)

        if isinstance(last_exception, USGSAPIError):
            raise last_exception
        raise USGSAPIError(
            f"Se agotaron los {self.max_retries} intentos de consulta a la API del USGS: {last_exception}"
        ) from last_exception
