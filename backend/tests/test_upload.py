"""Upload endpoint: accepted files, rejected files, and the file-info endpoint."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from tests.helpers import (
    kml_document,
    line_xml,
    lonlat_square,
    placemark,
    point_xml,
    polygon_xml,
    shapefile_zip,
)

KML = kml_document(
    placemark("plot", polygon_xml(lonlat_square(77.0, 12.0))),
    placemark("road", line_xml([(77.0, 12.0), (77.01, 12.0)])),
    placemark("well", point_xml((77.005, 12.005))),
)


def test_upload_valid_kml(upload, settings):
    response = upload("survey.kml", KML)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"
    assert "error_message" not in body
    assert len(body["id"]) == 32


def test_upload_valid_shapefile_zip(upload):
    gdf = gpd.GeoDataFrame(
        {"owner": ["A", "B"]},
        geometry=[
            Polygon([(500000, 1400000), (500100, 1400000), (500100, 1400200), (500000, 1400200)]),
            Polygon([(501000, 1400000), (501050, 1400000), (501050, 1400050), (501000, 1400050)]),
        ],
        crs="EPSG:32643",
    )

    response = upload("parcels.zip", shapefile_zip(gdf))

    assert response.status_code == 201
    body = response.json()
    assert body["feature_count"] == 2
    assert body["crs"] == "EPSG:32643"
    assert body["status"] == "COMPLETED"


def test_upload_response_matches_get_file_info(upload, client):
    uploaded = upload("survey.kml", KML).json()

    info = client.get(f"/api/files/{uploaded['id']}/")

    assert info.status_code == 200
    body = info.json()
    assert body["id"] == uploaded["id"]
    assert body["status"] == "COMPLETED"
    assert body["created_at"].endswith("Z") or "+00:00" in body["created_at"]
    assert "updated_at" in body


def test_get_unknown_file_returns_404(client):
    response = client.get("/api/files/does-not-exist/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.parametrize(
    "name", ["notes.txt", "data.shp", "tour.kmz", "noextension", "evil.kml.exe"]
)
def test_unsupported_extension_is_rejected(upload, name):
    response = upload(name, b"whatever content")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_empty_upload_is_rejected(upload):
    response = upload("empty.kml", b"")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_missing_file_field_returns_422(client):
    response = client.post("/api/files/")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any("file" in detail["field"] for detail in error["details"])


def test_non_zip_content_with_zip_extension_is_rejected(upload):
    response = upload("fake.zip", b"this is definitely not a zip file")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_CONTENT"


def test_corrupt_zip_is_rejected(upload):
    valid = shapefile_zip(
        gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:32643")
    )
    truncated = valid[: len(valid) // 2]

    response = upload("broken.zip", truncated)

    assert response.status_code == 400
    assert response.json()["error"]["code"] in {"INVALID_ARCHIVE", "INVALID_FILE_CONTENT"}


def test_non_kml_content_with_kml_extension_is_rejected(upload):
    response = upload("fake.kml", b"\x00\x01\x02 binary garbage")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_CONTENT"


@pytest.mark.parametrize("extra_bytes", [100 * 1024, 1000])
def test_file_over_size_limit_returns_413(upload, extra_bytes):
    """Covers both the early Content-Length check and the streaming read check."""
    oversized = KML + b" " * (1024 * 1024 + extra_bytes)

    response = upload("big.kml", oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.parametrize(
    ("client_name", "expected_display"),
    [
        ("../../etc/passwd.kml", "passwd.kml"),
        ("..\\..\\windows\\evil.kml", "evil.kml"),
        ("C:\\Users\\me\\survey.kml", "survey.kml"),
    ],
)
def test_client_filename_is_never_used_as_a_path(upload, settings, client_name, expected_display):
    response = upload(client_name, KML)

    assert response.status_code == 201
    assert response.json()["filename"] == expected_display
    stored = [p for p in settings.upload_dir.rglob("*") if p.is_file()]
    assert len(stored) == 1
    assert stored[0].parent == settings.upload_dir
    assert stored[0].stem == response.json()["id"]
    assert stored[0].suffix == ".kml"


def test_rejected_upload_stores_nothing(upload, settings):
    upload("notes.txt", b"hello")
    upload("empty.kml", b"")

    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())
