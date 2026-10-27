"""Cliente HTTP para la API REST de OpenMetadata v1 con autenticación y manejo no bloqueante."""
import logging
import re
from typing import Any, Optional

import httpx
from src.common.config import get_settings


logger = logging.getLogger(__name__)


class OpenMetadataClient:
    """Cliente para interactuar con la API REST de OpenMetadata."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 10):
        settings = get_settings()
        self.base_url = (base_url or settings.metadata.server_url).rstrip("/")
        self.token = token or settings.metadata.jwt_token
        self.timeout = timeout
        self.api_url = f"{self.base_url}/api/v1"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def is_healthy(self) -> bool:
        """Comprueba si el servidor OpenMetadata está activo y responde en /api/v1/system/version."""
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{self.api_url}/system/version", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    def create_or_update_classification(self, name: str, description: str) -> Optional[dict[str, Any]]:
        """Crea o actualiza una categoría de clasificación de etiquetas."""
        url = f"{self.api_url}/classifications"
        payload = {"name": name, "description": description}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.warning("No se pudo registrar clasificación %s: %s", name, resp.text)
                return None
        except Exception as exc:
            logger.warning("Error conectando a OpenMetadata para clasificación %s: %s", name, exc)
            return None

    def create_or_update_tag(self, classification: str, name: str, description: str) -> Optional[dict[str, Any]]:
        """Crea o actualiza una etiqueta dentro de una clasificación."""
        url = f"{self.api_url}/tags"
        payload = {
            "name": name,
            "classification": classification,
            "description": description,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                return None
        except Exception as exc:
            logger.debug("Error registrando etiqueta %s.%s: %s", classification, name, exc)
            return None

    def create_or_update_database_service(
        self,
        name: str,
        host_port: str,
        username: str,
        database: str,
        password: Optional[str] = None,
        description: str = "Servicio PostgreSQL del Almacén Sísmico Medallón",
    ) -> Optional[dict[str, Any]]:
        """Registra el servicio de base de datos PostgreSQL en OpenMetadata."""
        url = f"{self.api_url}/services/databaseServices"
        config: dict[str, Any] = {
            "type": "Postgres",
            "hostPort": host_port,
            "username": username,
            "database": database,
        }
        if password:
            config["authType"] = {"password": password}

        payload = {
            "name": name,
            "serviceType": "Postgres",
            "description": description,
            "connection": {
                "config": config
            },
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.warning("Fallo al registrar servicio de BD %s: %s", name, resp.text)
                return None
        except Exception as exc:
            logger.warning("Error conectando al crear servicio de BD %s: %s", name, exc)
            return None

    def create_or_update_database(
        self, service_name: str, database_name: str, description: str
    ) -> Optional[dict[str, Any]]:
        """Registra una base de datos bajo un servicio de base de datos."""
        url = f"{self.api_url}/databases"
        payload = {
            "name": database_name,
            "service": service_name,
            "description": description,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                return None
        except Exception as exc:
            logger.debug("Error registrando base de datos %s: %s", database_name, exc)
            return None

    def create_or_update_schema(
        self, database_fqn: str, schema_name: str, description: str
    ) -> Optional[dict[str, Any]]:
        """Registra un esquema dentro de una base de datos."""
        url = f"{self.api_url}/databaseSchemas"
        payload = {
            "name": schema_name,
            "database": database_fqn,
            "description": description,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                return None
        except Exception as exc:
            logger.debug("Error registrando esquema %s: %s", schema_name, exc)
            return None

    def create_or_update_table(
        self,
        schema_fqn: str,
        table_name: str,
        columns: list[dict[str, Any]],
        description: str,
        tags: Optional[list[str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Registra una tabla con sus columnas, tipos, descripciones y etiquetas."""
        url = f"{self.api_url}/tables"

        om_columns = []
        for col in columns:
            col_type = col.get("type", "VARCHAR").upper()
            dataType = "VARCHAR"
            if "BIGINT" in col_type:
                dataType = "BIGINT"
            elif "INT" in col_type:
                dataType = "INT"
            elif "NUMERIC" in col_type or "FLOAT" in col_type or "DOUBLE" in col_type:
                dataType = "NUMERIC"
            elif "BOOL" in col_type:
                dataType = "BOOLEAN"
            elif "TIME" in col_type or "DATE" in col_type:
                dataType = "TIMESTAMP"
            elif "JSON" in col_type:
                dataType = "JSON"
            elif "UUID" in col_type:
                dataType = "UUID"

            col_def: dict[str, Any] = {
                "name": col["name"],
                "dataType": dataType,
                "description": col.get("description", ""),
            }

            if dataType in ("VARCHAR", "CHAR", "BINARY", "VARBINARY"):
                match = re.search(r"\((\d+)\)", col_type)
                col_def["dataLength"] = int(match.group(1)) if match else 255

            om_columns.append(col_def)

        payload: dict[str, Any] = {
            "name": table_name,
            "databaseSchema": schema_fqn,
            "columns": om_columns,
            "description": description,
        }

        if tags:
            payload["tags"] = [{"tagFQN": tag, "source": "Classification"} for tag in tags]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.warning("Fallo al registrar tabla %s.%s: %s", schema_fqn, table_name, resp.text)
                return None
        except Exception as exc:
            logger.debug("Error registrando tabla %s: %s", table_name, exc)
            return None

    def add_lineage_edge(
        self, from_table_id: str, to_table_id: str, description: Optional[str] = None
    ) -> bool:
        """Registra una arista de linaje directo entre dos entidades."""
        url = f"{self.api_url}/lineage"
        payload = {
            "edge": {
                "fromEntity": {"id": from_table_id, "type": "table"},
                "toEntity": {"id": to_table_id, "type": "table"},
                "description": description or "Transformación de pipeline",
            }
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(url, json=payload, headers=self._headers())
                return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Error registrando arista de linaje: %s", exc)
            return False

    def get_table_by_fqn(self, fqn: str) -> Optional[dict[str, Any]]:
        """Obtiene una tabla por su Fully Qualified Name (FQN)."""
        url = f"{self.api_url}/tables/name/{fqn}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception:
            return None
