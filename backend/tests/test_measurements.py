"""Measurement endpoint: values must be metric and agree with an independent reference."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from tests.helpers import (
    geodesic_area,
    geodesic_length,
    kml_document,
    line_xml,
    lonlat_square,
    placemark,
    point_xml,
    polygon_xml,
    shapefile_zip,
)

RING = lonlat_square(77.0, 12.0)
LINE = [(77.0, 12.0), (77.01, 12.0), (77.01, 12.01)]
KML = kml_document(
    placemark("plot", polygon_xml(RING)),
    placemark("road", line_xml(LINE)),
    placemark("well", point_xml((77.005, 12.005))),
)


def measurements_of(upload, client, name, content):
    file_id = upload(name, content).json()["id"]
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    return response.json()


def test_kml_polygon_area_is_in_square_metres(upload, client):
    body = measurements_of(upload, client, "s.kml", KML)

    polygon = body["measurements"][0]
    assert polygon["geometry_type"] == "Polygon"
    assert polygon["unit"] == "m²"
    assert polygon["length"] is None
    assert polygon["area"] == pytest.approx(geodesic_area(RING), rel=0.005)
    assert polygon["area"] > 1_000_000  # ~1.2 km², not 0.0001 "square degrees"
    assert polygon["calculation_crs"] == "EPSG:32643"
    assert polygon["status"] == "MEASURED"


def test_kml_linestring_length_is_in_metres(upload, client):
    body = measurements_of(upload, client, "s.kml", KML)

    line = body["measurements"][1]
    assert line["geometry_type"] == "LineString"
    assert line["unit"] == "m"
    assert line["area"] is None
    assert line["length"] == pytest.approx(geodesic_length(LINE), rel=0.005)


def test_point_has_no_measurement(upload, client):
    body = measurements_of(upload, client, "s.kml", KML)

    point = body["measurements"][2]
    assert point["geometry_type"] == "Point"
    assert point["area"] is None
    assert point["length"] is None
    assert point["unit"] is None
    assert point["status"] == "NOT_APPLICABLE"


def test_response_shape(upload, client):
    body = measurements_of(upload, client, "s.kml", KML)

    assert set(body) == {"file_id", "crs", "measurements"}
    assert body["crs"] == "EPSG:4326"
    assert [m["feature_id"] for m in body["measurements"]] == [0, 1, 2]


@pytest.mark.parametrize(
    ("geometry", "field", "expected"),
    [
        (
            Polygon([(500000, 1400000), (500100, 1400000), (500100, 1400200), (500000, 1400200)]),
            "area",
            20_000.0,
        ),
        (LineString([(500000, 1400000), (500300, 1400400)]), "length", 500.0),  # 3-4-5 triangle
    ],
)
def test_projected_shapefile_is_measured_directly_in_its_own_crs(
    upload, client, geometry, field, expected
):
    gdf = gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:32643")

    item = measurements_of(upload, client, "p.zip", shapefile_zip(gdf))["measurements"][0]

    assert item[field] == pytest.approx(expected)
    assert item["calculation_crs"] == "EPSG:32643"


def test_point_shapefile_has_no_measurement(upload, client):
    gdf = gpd.GeoDataFrame(geometry=[Point(500000, 1400000)], crs="EPSG:32643")

    item = measurements_of(upload, client, "pt.zip", shapefile_zip(gdf))["measurements"][0]

    assert item["status"] == "NOT_APPLICABLE"
    assert item["area"] is None and item["length"] is None


def test_multipolygon_area_is_summed(upload, client):
    square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    other = Polygon([(500, 500), (600, 500), (600, 550), (500, 550)])
    gdf = gpd.GeoDataFrame(geometry=[MultiPolygon([square, other])], crs="EPSG:32643")

    body = measurements_of(upload, client, "m.zip", shapefile_zip(gdf))

    assert body["measurements"][0]["geometry_type"] == "MultiPolygon"
    assert body["measurements"][0]["area"] == pytest.approx(15_000.0)


def test_features_endpoint_returns_geometry_and_properties(upload, client):
    kml = kml_document(placemark("plot A", polygon_xml(RING)))
    file_id = upload("s.kml", kml).json()["id"]

    response = client.get(f"/api/files/{file_id}/features/")

    assert response.status_code == 200
    feature = response.json()["features"][0]
    assert feature["feature_id"] == 0
    assert feature["geometry_type"] == "Polygon"
    assert feature["properties"]["Name"] == "plot A"
    assert feature["geometry"]["type"] == "Polygon"
    assert all(len(position) == 2 for position in feature["geometry"]["coordinates"][0])


def test_measurements_for_unknown_file_returns_404(client):
    response = client.get("/api/files/unknown/measurements/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_features_for_unknown_file_returns_404(client):
    assert client.get("/api/files/unknown/features/").status_code == 404
