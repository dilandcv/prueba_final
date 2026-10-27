"""Servicio de ingesta de datos hacia la capa Bronze en PostgreSQL."""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional
import uuid
from psycopg import Cursor
from psycopg.types.json import Jsonb
from src.common.config import get_settings
from src.common.db import get_db_connection
from src.ingestion.usgs_client import USGSClient


logger = logging.getLogger(__name__)


class USGSIngestionService:
    """Orquesta la extracción de datos desde USGS y su almacenamiento append-only en Bronze."""

    def __init__(self, client: Optional[USGSClient] = None) -> None:
        self.client = client or USGSClient()
        self.settings = get_settings()

    def get_watermark(self, cursor: Cursor) -> Optional[datetime]:
        """Obtiene la marca temporal de la última ingesta exitosa desde la tabla de control."""
        cursor.execute(
            """
            SELECT last_success_timestamp
            FROM ops.ingestion_watermark
            WHERE source_name = 'usgs';
            """
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def save_watermark(
        self,
        cursor: Cursor,
        last_success_timestamp: datetime,
        batch_id: uuid.UUID,
    ) -> None:
        """Persiste de forma atómica la marca de agua tras una ingesta completada."""
        cursor.execute(
            """
            INSERT INTO ops.ingestion_watermark (
                source_name,
                last_success_timestamp,
                last_batch_id,
                updated_at
            )
            VALUES ('usgs', %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (source_name) DO UPDATE SET
                last_success_timestamp = EXCLUDED.last_success_timestamp,
                last_batch_id = EXCLUDED.last_batch_id,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (last_success_timestamp, batch_id),
        )

    def insert_bronze_records(
        self,
        cursor: Cursor,
        batch_id: uuid.UUID,
        features: list[dict[str, Any]],
    ) -> int:
        """Inserta eventos crudos en Bronze. Garantiza idempotencia ante reintentos del mismo batch_id."""
        if not features:
            return 0

        # Si el lote fue parcialmente insertado en un intento previo que falló, se limpia ese batch_id específico
        cursor.execute(
            "DELETE FROM bronze.earthquakes WHERE batch_id = %s;",
            (batch_id,),
        )

        records_to_insert = []
        for feature in features:
            event_id = feature.get("id") or str(feature.get("properties", {}).get("code", "unknown"))

            # Conversión de milisegundos epoch reportados por USGS a timestamp UTC
            updated_ms = feature.get("properties", {}).get("updated")
            if updated_ms is not None:
                source_updated_at = datetime.fromtimestamp(updated_ms / 1000.0, tz=timezone.utc)
            else:
                source_updated_at = datetime.now(timezone.utc)

            # Conservación íntegra del JSON original en la columna JSONB
            payload_json = Jsonb(feature)

            records_to_insert.append((
                event_id,
                batch_id,
                source_updated_at,
                payload_json,
            ))

        cursor.executemany(
            """
            INSERT INTO bronze.earthquakes (
                event_id,
                batch_id,
                source_updated_at,
                payload
            ) VALUES (%s, %s, %s, %s);
            """,
            records_to_insert,
        )

        return len(records_to_insert)

    def run(self, batch_id: Optional[uuid.UUID] = None) -> dict[str, Any]:
        """Ejecuta el ciclo completo de ingesta con manejo transaccional en PostgreSQL."""
        current_batch_id = batch_id or uuid.uuid4()
        now_utc = datetime.now(timezone.utc)

        with get_db_connection(role="pipeline") as conn:
            with conn.cursor() as cur:
                # 1. Obtención de marca de agua
                watermark = self.get_watermark(cur)

                if watermark:
                    logger.info("Ingesta incremental: consultando eventos con updatedafter >= %s", watermark)
                    features = self.client.fetch_events(updatedafter=watermark)
                    is_initial_load = False
                else:
                    initial_lookback = timedelta(days=self.settings.usgs.initial_lookback_days)
                    starttime = now_utc - initial_lookback
                    logger.info("Primera carga: consultando eventos desde starttime >= %s", starttime)
                    features = self.client.fetch_events(starttime=starttime, endtime=now_utc)
                    is_initial_load = True

                # 2. Inserción append-only en Bronze
                inserted_count = self.insert_bronze_records(cur, current_batch_id, features)

                # 3. Determinación y actualización de la nueva marca de agua
                # Si vinieron eventos, tomamos el mayor source_updated_at; de lo contrario el tiempo actual
                if features:
                    latest_update_ms = max(
                        f.get("properties", {}).get("updated", 0) for f in features
                    )
                    new_watermark = (
                        datetime.fromtimestamp(latest_update_ms / 1000.0, tz=timezone.utc)
                        if latest_update_ms > 0
                        else now_utc
                    )
                else:
                    new_watermark = watermark or now_utc

                self.save_watermark(cur, new_watermark, current_batch_id)

                # 4. Confirmación de la transacción
                conn.commit()

        logger.info(
            "Ciclo de ingesta completado. Batch: %s, Registros: %d, Nueva marca de agua: %s",
            current_batch_id,
            inserted_count,
            new_watermark,
        )

        return {
            "batch_id": str(current_batch_id),
            "records_ingested": inserted_count,
            "is_initial_load": is_initial_load,
            "watermark": new_watermark.isoformat(),
            "status": "SUCCESS",
        }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    service = USGSIngestionService()
    summary = service.run()
    print(f"Ingesta finalizada: {summary}")
