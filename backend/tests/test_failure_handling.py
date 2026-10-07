"""One bad feature must not break the file; bad files must not crash or leak details."""

import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.services import file_service
from tests.helpers import (
    kml_document,
    line_xml,
    lonlat_square,
    placemark,
    point_xml,
    polygon_xml,
    shapefile_members,
    zip_bytes,
)

GOOD_RING = lonlat_square(77.0, 12.0)
BOWTIE = [(77.0, 12.0), (77.01, 12.01), (77.01, 12.0), (77.0, 12.01), (77.0, 12.0)]
MULTI_GEOMETRY = (
    "<MultiGeometry>"
    f"{point_xml((77.0, 12.0))}{line_xml([(77.0, 12.0), (77.1, 12.1)])}"
    "</MultiGeometry>"
)
MIXED_KML = kml_document(
    placemark("good polygon", polygon_xml(GOOD_RING)),
    placemark("mixed collection", MULTI_GEOMETRY),
    placemark("no geometry"),
    placemark("bowtie", polygon_xml(BOWTIE)),
    placemark("good line", line_xml([(77.0, 12.0), (77.01, 12.0)])),
)

LEAK_MARKERS = ["Traceback", 'File "', "/tmp", "\\Temp", ".py", "pyogrio", "GDAL"]


def assert_no_internal_details(text: str, tmp_path) -> None:
    for marker in LEAK_MARKERS + [str(tmp_path)]:
        assert marker not in text


def test_bad_features_do_not_stop_the_other_features(upload, client):
    uploaded = upload("mixed.kml", MIXED_KML).json()

    assert uploaded["status"] == "COMPLETED"
    assert uploaded["feature_count"] == 5
    by_name = {
        m["feature_id"]: m
        for m in client.get(f"/api/files/{uploaded['id']}/measurements/").json()["measurements"]
    }
    assert by_name[0]["status"] == "MEASURED" and by_name[0]["area"] > 0
    assert by_name[4]["status"] == "MEASURED" and by_name[4]["length"] > 0


def test_unsupported_geometry_is_reported_not_fatal(upload, client):
    file_id = upload("mixed.kml", MIXED_KML).json()["id"]

    item = client.get(f"/api/files/{file_id}/measurements/").json()["measurements"][1]

    assert item["geometry_type"] == "GeometryCollection"
    assert item["status"] == "UNSUPPORTED"
    assert item["area"] is None and item["length"] is None
    assert "not supported" in item["note"]


def test_feature_without_geometry_is_flagged_invalid(upload, client):
    file_id = upload("mixed.kml", MIXED_KML).json()["id"]

    item = client.get(f"/api/files/{file_id}/measurements/").json()["measurements"][2]

    assert item["geometry_type"] is None
    assert item["status"] == "INVALID"
    assert item["note"] == "The feature has no geometry."


def test_self_intersecting_polygon_is_not_measured(upload, client):
    file_id = upload("mixed.kml", MIXED_KML).json()["id"]

    item = client.get(f"/api/files/{file_id}/measurements/").json()["measurements"][3]

    assert item["status"] == "INVALID"
    assert item["area"] is None
    assert item["note"].startswith("Invalid geometry")


def test_truncated_kml_is_rejected_without_leaking_details(upload, settings, tmp_path):
    truncated = MIXED_KML[: len(MIXED_KML) // 2]

    response = upload("cut.kml", truncated)

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "INVALID_FILE_CONTENT",
        "message": "The file is not a valid KML document.",
    }
    assert_no_internal_details(response.text, tmp_path)
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


def test_kml_without_features_fails_cleanly(upload):
    body = upload("empty-doc.kml", kml_document()).json()

    assert body["status"] == "FAILED"
    assert body["error_message"] == "The KML file contains no features."


def test_corrupt_shapefile_content_fails_cleanly(upload, tmp_path):
    members = shapefile_members(
        gpd.GeoDataFrame(geometry=[Point(500000, 1400000)], crs="EPSG:32643")
    )
    members["layer.shp"] = b"this is not shapefile data" * 20

    response = upload("corrupt.zip", zip_bytes(members))

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["error_message"] == "The Shapefile could not be read."
    assert_no_internal_details(response.text, tmp_path)


def test_failed_file_info_includes_error_message(upload, client):
    file_id = upload("empty-doc.kml", kml_document()).json()["id"]

    body = client.get(f"/api/files/{file_id}/").json()

    assert body["status"] == "FAILED"
    assert body["error_message"] == "The KML file contains no features."


def test_unexpected_processing_error_is_hidden_from_client(upload, monkeypatch, tmp_path):
    def explode(*args, **kwargs):
        raise RuntimeError("secret detail at /etc/passwd")

    monkeypatch.setattr(file_service, "process_file", explode)

    response = upload("survey.kml", MIXED_KML)

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert "secret" not in response.text and "/etc/passwd" not in response.text


def test_unexpected_server_error_returns_generic_500(client, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(file_service, "get_file_or_404", explode)

    response = client.get("/api/files/abc/")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }


@pytest.mark.parametrize(("method", "path"), [("get", "/nope"), ("delete", "/api/files/")])
def test_unknown_routes_use_the_same_error_shape(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code in {404, 405}
    assert set(response.json()) == {"error"}
    assert {"code", "message"} <= set(response.json()["error"])


def test_swagger_and_redoc_are_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200
