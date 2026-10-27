"""Pruebas unitarias y de integración para OpenMetadata (Fase 11).

Verifica:
1. Definición completa del catálogo: esquemas, tablas, descripciones y etiquetas Medallón.
2. Definición del grafo de linaje de datos de extremo a extremo.
3. Resiliencia no bloqueante del cliente cuando OpenMetadata no está disponible.
4. Sincronización exitosa con mocks de la API REST de OpenMetadata.
5. Integración no bloqueante de la tarea de Airflow.
6. Especificaciones de Docker Compose (perfiles, ausencia de dependencias circulares y límites de memoria).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml

import pytest
from src.metadata.catalog import CLASSIFICATIONS, LINEAGE_EDGES, TABLES_CATALOG
from src.metadata.client import OpenMetadataClient
from src.metadata.service import sync_metadata_catalog
from src.pipeline.tasks import sync_metadata_task


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. Pruebas de Definición del Catálogo y Etiquetas
# ==============================================================================
def test_classifications_and_medallion_tags_defined():
    """Garantiza que existan las clasificaciones Medallion (Bronze, Silver, Gold) y Governance."""
    classif_names = [c["name"] for c in CLASSIFICATIONS]
    assert "Medallion" in classif_names
    assert "Governance" in classif_names

    medallion = next(c for c in CLASSIFICATIONS if c["name"] == "Medallion")
    tag_names = [t["name"] for t in medallion["tags"]]
    assert "Bronze" in tag_names
    assert "Silver" in tag_names
    assert "Gold" in tag_names


def test_tables_catalog_covers_all_architecture_layers():
    """Verifica que el catálogo cubra las tablas de Bronze, Silver, Gold, Metrics y Ops."""
    schemas = {t["schema"] for t in TABLES_CATALOG}
    assert "bronze" in schemas
    assert "silver" in schemas
    assert "gold" in schemas
    assert "metrics" in schemas
    assert "ops" in schemas

    table_names = {f"{t['schema']}.{t['name']}" for t in TABLES_CATALOG}
    assert "bronze.earthquakes" in table_names
    assert "silver.earthquakes" in table_names
    assert "gold.earthquakes" in table_names
    assert "gold.hourly_regional_stats" in table_names
    assert "gold.magnitude_distribution" in table_names
    assert "gold.regional_ranking" in table_names
    assert "metrics.data_quality" in table_names
    assert "ops.anomaly_alerts" in table_names

    # Verificar que cada tabla tenga descripción y columnas documentadas
    for tbl in TABLES_CATALOG:
        assert tbl.get("description"), f"Tabla {tbl['name']} carece de descripción"
        assert len(tbl.get("columns", [])) > 0, f"Tabla {tbl['name']} no tiene columnas"
        for col in tbl["columns"]:
            assert "name" in col
            assert "type" in col
            assert "description" in col


def test_data_lineage_graph_completeness():
    """Verifica que el grafo de linaje conecte correctamente Bronze -> Silver -> Gold -> Ops."""
    lineage_map = {(edge["from"], edge["to"]): edge["description"] for edge in LINEAGE_EDGES}

    # Bronze -> Silver
    assert any(
        "bronze.earthquakes" in src and "silver.earthquakes" in dst
        for (src, dst) in lineage_map.keys()
    )

    # Silver -> Gold
    assert any(
        "silver.earthquakes" in src and "gold.earthquakes" in dst
        for (src, dst) in lineage_map.keys()
    )
    assert any(
        "silver.earthquakes" in src and "gold.hourly_regional_stats" in dst
        for (src, dst) in lineage_map.keys()
    )

    # Gold -> Ops (Anomalías)
    assert any(
        "gold.hourly_regional_stats" in src and "ops.anomaly_alerts" in dst
        for (src, dst) in lineage_map.keys()
    )


# ==============================================================================
# 2. Pruebas de Resiliencia del Cliente (Mejor Esfuerzo No Bloqueante)
# ==============================================================================
def test_client_is_healthy_false_when_unreachable():
    """Garantiza que el cliente no lance excepción si el servidor OpenMetadata está caído."""
    client = OpenMetadataClient(base_url="http://non-existent-openmetadata:8585", timeout=1)
    assert client.is_healthy() is False


def test_sync_metadata_catalog_graceful_skip_when_offline():
    """Verifica que la sincronización se omita de forma no bloqueante si OpenMetadata está offline."""
    client = OpenMetadataClient(base_url="http://non-existent-openmetadata:8585", timeout=1)
    res = sync_metadata_catalog(client)
    assert res["status"] == "SKIPPED"
    assert "not reachable" in res["reason"].lower()
    assert res["tables_registered"] == 0


def test_sync_metadata_airflow_task_non_blocking():
    """Verifica que la tarea de Airflow se ejecute sin interrumpir el pipeline si el servidor no responde."""
    with patch("src.metadata.client.OpenMetadataClient.is_healthy", return_value=False):
        res = sync_metadata_task()
        assert res["status"] == "SKIPPED"


# ==============================================================================
# 3. Pruebas de Sincronización Completa con Mocks de API REST
# ==============================================================================
def test_sync_metadata_catalog_success_with_mocked_server():
    """Verifica el flujo completo de sincronización de metadatos cuando el servidor responde."""
    mock_client = OpenMetadataClient(base_url="http://mock-openmetadata:8585")

    # Mocks de respuestas de OpenMetadata
    mock_client.is_healthy = MagicMock(return_value=True)
    mock_client.create_or_update_classification = MagicMock(return_value={"id": "cls-1"})
    mock_client.create_or_update_tag = MagicMock(return_value={"id": "tag-1"})
    mock_client.create_or_update_database_service = MagicMock(return_value={"id": "svc-1"})
    mock_client.create_or_update_database = MagicMock(return_value={"id": "db-1"})
    mock_client.create_or_update_schema = MagicMock(return_value={"id": "sch-1"})

    def mock_create_table(schema_fqn, table_name, columns, description, tags=None):
        return {
            "id": f"tbl-{table_name}",
            "name": table_name,
            "fullyQualifiedName": f"{schema_fqn}.{table_name}",
        }

    mock_client.create_or_update_table = MagicMock(side_effect=mock_create_table)
    mock_client.add_lineage_edge = MagicMock(return_value=True)

    result = sync_metadata_catalog(mock_client)

    assert result["status"] == "SUCCESS"
    assert result["tables_registered"] == len(TABLES_CATALOG)
    assert result["tags_registered"] > 0
    assert result["lineage_edges_created"] == len(LINEAGE_EDGES)

    assert mock_client.create_or_update_database_service.called
    assert mock_client.create_or_update_database.called
    assert mock_client.create_or_update_table.call_count == len(TABLES_CATALOG)
    assert mock_client.add_lineage_edge.call_count == len(LINEAGE_EDGES)


# ==============================================================================
# 4. Pruebas de Configuración Docker Compose
# ==============================================================================
def test_docker_compose_metadata_profile_and_non_circular_dependencies():
    """Garantiza la configuración de OpenMetadata en Docker Compose sin dependencias circulares."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists()

    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})

    # Verificar que los 4 servicios de OpenMetadata estén declarados
    assert "elasticsearch" in services
    assert "openmetadata-migrate" in services
    assert "openmetadata-server" in services
    assert "openmetadata-ingestion" in services

    # Todos deben estar bajo el perfil metadata
    for s_name in ["elasticsearch", "openmetadata-migrate", "openmetadata-server", "openmetadata-ingestion"]:
        assert "metadata" in services[s_name].get("profiles", [])

    # Verificar cadena de dependencias estrictamente no circular
    migrate_deps = services["openmetadata-migrate"].get("depends_on", {})
    assert "postgres" in migrate_deps
    assert "elasticsearch" in migrate_deps

    server_deps = services["openmetadata-server"].get("depends_on", {})
    assert "openmetadata-migrate" in server_deps
    assert "elasticsearch" in server_deps

    ingest_deps = services["openmetadata-ingestion"].get("depends_on", {})
    assert "openmetadata-server" in ingest_deps

    # Verificar que la memoria de Elasticsearch esté acotada
    es_env = services["elasticsearch"].get("environment", [])
    es_env_str = str(es_env)
    assert "-Xms512m -Xmx512m" in es_env_str
