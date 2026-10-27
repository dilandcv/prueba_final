"""Servicio de sincronización y descubrimiento de metadatos con OpenMetadata."""
import logging
from typing import Any, Optional

from src.common.config import get_settings
from src.metadata.catalog import CLASSIFICATIONS, LINEAGE_EDGES, TABLES_CATALOG
from src.metadata.client import OpenMetadataClient


logger = logging.getLogger(__name__)


def sync_metadata_catalog(client: Optional[OpenMetadataClient] = None) -> dict[str, Any]:
    """Descubre e ingesta de forma automatizada los esquemas, tablas, etiquetas y linaje."""
    settings = get_settings()
    om_client = client or OpenMetadataClient()

    logger.info("Comprobando disponibilidad del servidor OpenMetadata en %s...", om_client.base_url)

    if not om_client.is_healthy():
        logger.warning(
            "Servidor OpenMetadata no disponible en %s. Omitiendo sincronización de metadatos "
            "de forma no bloqueante (modo mejor esfuerzo).",
            om_client.base_url,
        )
        return {
            "status": "SKIPPED",
            "reason": "OpenMetadata server is not reachable",
            "tables_registered": 0,
            "lineage_edges_created": 0,
        }

    logger.info("OpenMetadata responde correctamente. Iniciando sincronización del catálogo Medallón...")

    # 1. Registrar clasificaciones y etiquetas de gobierno
    tags_count = 0
    for cls_data in CLASSIFICATIONS:
        c_name = cls_data["name"]
        om_client.create_or_update_classification(c_name, cls_data["description"])
        for tag in cls_data["tags"]:
            om_client.create_or_update_tag(c_name, tag["name"], tag["description"])
            tags_count += 1

    # 2. Registrar Servicio de Base de Datos PostgreSQL
    service_name = "postgres_seismic"
    host_port = f"{settings.db.host}:{settings.db.port}"
    om_client.create_or_update_database_service(
        name=service_name,
        host_port=host_port,
        username=settings.db.user,
        database=settings.db.name,
    )

    # 3. Registrar Base de Datos
    db_name = settings.db.name
    om_client.create_or_update_database(
        service_name=service_name,
        database_name=db_name,
        description="Almacén de datos sísmicos con arquitectura Medallón (USGS)",
    )

    db_fqn = f"{service_name}.{db_name}"

    # 4. Registrar Esquemas
    schemas = {"bronze", "silver", "gold", "metrics", "ops"}
    for sch in schemas:
        om_client.create_or_update_schema(
            database_fqn=db_fqn,
            schema_name=sch,
            description=f"Capa arquitectónica y operativa '{sch}' de la plataforma",
        )

    # 5. Registrar Tablas y Columnas con sus Etiquetas
    tables_registered = 0
    table_id_map: dict[str, str] = {}

    for tbl in TABLES_CATALOG:
        schema_fqn = f"{db_fqn}.{tbl['schema']}"
        created_tbl = om_client.create_or_update_table(
            schema_fqn=schema_fqn,
            table_name=tbl["name"],
            columns=tbl["columns"],
            description=tbl["description"],
            tags=tbl.get("tags"),
        )
        if created_tbl:
            tables_registered += 1
            fqn = created_tbl.get("fullyQualifiedName") or f"{schema_fqn}.{tbl['name']}"
            if "id" in created_tbl:
                table_id_map[fqn] = created_tbl["id"]

    # 6. Registrar Linaje de Datos (Mejor Esfuerzo)
    lineage_created = 0
    for edge in LINEAGE_EDGES:
        from_fqn = edge["from"]
        to_fqn = edge["to"]

        from_id = table_id_map.get(from_fqn)
        to_id = table_id_map.get(to_fqn)

        # Si no están en caché, intentar obtenerlos por API
        if not from_id:
            from_entity = om_client.get_table_by_fqn(from_fqn)
            from_id = from_entity.get("id") if from_entity else None
        if not to_id:
            to_entity = om_client.get_table_by_fqn(to_fqn)
            to_id = to_entity.get("id") if to_entity else None

        if from_id and to_id:
            success = om_client.add_lineage_edge(
                from_table_id=from_id,
                to_table_id=to_id,
                description=edge.get("description"),
            )
            if success:
                lineage_created += 1

    logger.info(
        "Sincronización de metadatos finalizada exitosamente: %d tablas, %d etiquetas, %d enlaces de linaje.",
        tables_registered,
        tags_count,
        lineage_created,
    )

    return {
        "status": "SUCCESS",
        "service": service_name,
        "database": db_name,
        "tables_registered": tables_registered,
        "tags_registered": tags_count,
        "lineage_edges_created": lineage_created,
        "server_url": om_client.base_url,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = sync_metadata_catalog()
    print(result)
