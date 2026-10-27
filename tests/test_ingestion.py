"""Pruebas unitarias para el cliente y servicio de ingesta de la API del USGS."""
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import pytest
from requests.exceptions import HTTPError, Timeout
from src.ingestion.service import USGSIngestionService
from src.ingestion.usgs_client import USGSAPIError, USGSClient


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_geojson():
    """Carga el fixture determinista de respuesta válida de USGS."""
    with open(FIXTURES_DIR / "usgs_sample.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def empty_geojson():
    """Carga el fixture determinista de respuesta vacía de USGS."""
    with open(FIXTURES_DIR / "usgs_empty.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------
# 1. Pruebas del Cliente HTTP (USGSClient)
# ------------------------------------------------------------------------------

def test_build_query_params_default(default_settings):
    """Verifica la construcción por defecto de los parámetros de consulta."""
    client = USGSClient()
    params = client.build_query_params()
    assert params["format"] == "geojson"
    assert params["minmagnitude"] == default_settings.usgs.min_magnitude
    assert params["orderby"] == "time-asc"
    assert params["limit"] == 20000
    assert "updatedafter" not in params


def test_build_query_params_updatedafter():
    """Verifica el uso de updatedafter en formato ISO 8601 UTC."""
    client = USGSClient()
    watermark = datetime(2026, 10, 20, 15, 30, 0, tzinfo=timezone.utc)
    params = client.build_query_params(updatedafter=watermark)
    assert params["updatedafter"] == "2026-10-20T15:30:00+00:00"
    assert "starttime" not in params


def test_fetch_events_success(sample_geojson):
    """Verifica la obtención y parseo correcto de una respuesta GeoJSON válida."""
    client = USGSClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_geojson

    with patch("requests.get", return_value=mock_resp) as mock_get:
        features = client.fetch_events(min_magnitude=3.0)

        assert len(features) == 2
        assert features[0]["id"] == "tx2024abcd"
        assert features[1]["id"] == "ci40123456"
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["minmagnitude"] == 3.0


def test_fetch_events_empty(empty_geojson):
    """Verifica que una respuesta con 0 eventos se gestione sin errores."""
    client = USGSClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = empty_geojson

    with patch("requests.get", return_value=mock_resp):
        features = client.fetch_events()
        assert features == []


def test_fetch_events_invalid_json():
    """Verifica que una respuesta que no es JSON válido lance USGSAPIError."""
    client = USGSClient(max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON")

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(USGSAPIError, match="no contiene JSON válido"):
            client.fetch_events()


def test_fetch_events_missing_features_key():
    """Verifica que un JSON sin clave 'features' lance USGSAPIError."""
    client = USGSClient(max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "message": "no features"}

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(USGSAPIError, match="falta la clave 'features'"):
            client.fetch_events()


def test_fetch_events_retries_on_http_error(sample_geojson):
    """Verifica que el cliente reintente ante errores 500 y devuelva datos al recuperarse."""
    client = USGSClient(max_retries=3, backoff_factor=0.01)

    error_resp = MagicMock()
    error_resp.status_code = 500
    error_resp.raise_for_status.side_effect = HTTPError("Internal Server Error")

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = sample_geojson

    # 1er intento falla (500), 2do intento tiene éxito (200)
    with patch("requests.get", side_effect=[error_resp, success_resp]) as mock_get:
        features = client.fetch_events()
        assert len(features) == 2
        assert mock_get.call_count == 2


def test_fetch_events_timeout_exhausts_retries():
    """Verifica que se agoten los reintentos ante un Timeout continuo."""
    client = USGSClient(max_retries=2, backoff_factor=0.01)

    with patch("requests.get", side_effect=Timeout("Gateway Timeout")):
        with pytest.raises(USGSAPIError, match="Se agotaron los 2 intentos"):
            client.fetch_events()


# ------------------------------------------------------------------------------
# 2. Pruebas del Servicio de Ingesta (USGSIngestionService)
# ------------------------------------------------------------------------------

def test_watermark_retrieval():
    """Verifica la consulta de la marca de agua en la base de datos."""
    service = USGSIngestionService()
    mock_cursor = MagicMock()

    # Caso 1: Hay marca de agua previa
    expected_dt = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchone.return_value = (expected_dt,)
    assert service.get_watermark(mock_cursor) == expected_dt

    # Caso 2: No hay marca de agua (primera carga)
    mock_cursor.fetchone.return_value = None
    assert service.get_watermark(mock_cursor) is None


def test_insert_bronze_records_and_payload_preservation(sample_geojson):
    """Verifica que el registro en Bronze conserve el batch_id, event_id y el JSON completo en JSONB."""
    service = USGSIngestionService()
    mock_cursor = MagicMock()
    test_batch_id = uuid.uuid4()

    count = service.insert_bronze_records(mock_cursor, test_batch_id, sample_geojson["features"])

    assert count == 2
    # Comprueba que se haya limpiado el batch antes de insertar
    mock_cursor.execute.assert_called_once_with(
        "DELETE FROM bronze.earthquakes WHERE batch_id = %s;",
        (test_batch_id,),
    )
    # Comprueba la inserción masiva
    mock_cursor.executemany.assert_called_once()
    sql_called, inserted_data = mock_cursor.executemany.call_args[0]
    assert "INSERT INTO bronze.earthquakes" in sql_called
    assert len(inserted_data) == 2

    # Verifica la estructura de la tupla insertada: (event_id, batch_id, source_updated_at, payload)
    first_record = inserted_data[0]
    assert first_record[0] == "tx2024abcd"
    assert first_record[1] == test_batch_id
    assert isinstance(first_record[2], datetime)
    # El payload debe ser un Jsonb conteniendo el feature completo original
    assert hasattr(first_record[3], "obj")
    assert first_record[3].obj["properties"]["place"] == "35 km SSE of Whites City, New Mexico"


def test_retry_same_batch_prevents_duplicates(sample_geojson):
    """Garantiza que reintentar una ingesta con el mismo batch_id elimine el intento parcial previo."""
    service = USGSIngestionService()
    mock_cursor = MagicMock()
    fixed_batch_id = uuid.uuid4()

    # Primer intento
    service.insert_bronze_records(mock_cursor, fixed_batch_id, sample_geojson["features"])
    # Segundo intento (reintento del mismo batch)
    service.insert_bronze_records(mock_cursor, fixed_batch_id, sample_geojson["features"])

    # Se debió llamar dos veces a DELETE para ese batch_id específico
    delete_calls = [
        call for call in mock_cursor.execute.call_args_list
        if "DELETE FROM bronze.earthquakes WHERE batch_id" in call[0][0]
    ]
    assert len(delete_calls) == 2
    assert delete_calls[0][0][1] == (fixed_batch_id,)
    assert delete_calls[1][0][1] == (fixed_batch_id,)


def test_service_initial_load_flow(sample_geojson):
    """Verifica el flujo de la primera carga: sin marca de agua previa, consulta por starttime."""
    mock_client = MagicMock(spec=USGSClient)
    mock_client.fetch_events.return_value = sample_geojson["features"]

    service = USGSIngestionService(client=mock_client)
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simula que no hay marca previa
    mock_cursor.fetchone.return_value = None

    with patch("src.ingestion.service.get_db_connection", return_value=mock_conn):
        result = service.run()

        assert result["status"] == "SUCCESS"
        assert result["is_initial_load"] is True
        assert result["records_ingested"] == 2
        # Debe haber llamado a fetch_events con starttime
        mock_client.fetch_events.assert_called_once()
        _, kwargs = mock_client.fetch_events.call_args
        assert "starttime" in kwargs
        assert "updatedafter" not in kwargs


def test_service_incremental_load_flow(sample_geojson):
    """Verifica el flujo incremental: con marca previa, consulta mediante updatedafter."""
    mock_client = MagicMock(spec=USGSClient)
    mock_client.fetch_events.return_value = sample_geojson["features"]

    service = USGSIngestionService(client=mock_client)
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simula marca de agua previa
    watermark = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchone.return_value = (watermark,)

    with patch("src.ingestion.service.get_db_connection", return_value=mock_conn):
        result = service.run()

        assert result["status"] == "SUCCESS"
        assert result["is_initial_load"] is False
        assert result["records_ingested"] == 2
        # Debe haber llamado a fetch_events con updatedafter
        mock_client.fetch_events.assert_called_once_with(updatedafter=watermark)


def test_event_updates_preserved_append_only(sample_geojson):
    """Garantiza que un evento modificado en origen se ingesta como nuevo registro sin sobreescribir Bronze."""
    service = USGSIngestionService()
    mock_cursor = MagicMock()

    batch_1 = uuid.uuid4()
    batch_2 = uuid.uuid4()

    # En lote 1 entra el evento original
    service.insert_bronze_records(mock_cursor, batch_1, [sample_geojson["features"][0]])

    # En lote 2 entra el mismo evento pero con fecha de modificación más reciente en origen
    updated_feature = dict(sample_geojson["features"][0])
    updated_feature["properties"] = dict(updated_feature["properties"])
    updated_feature["properties"]["updated"] = 1729009999000  # Más reciente

    service.insert_bronze_records(mock_cursor, batch_2, [updated_feature])

    # Ambas inserciones se ejecutaron independientemente conservando el historial append-only
    assert mock_cursor.executemany.call_count == 2
