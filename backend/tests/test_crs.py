"""CRS logic: never measure in degrees; choose a suitable metric CRS."""

import geopandas as gpd
import pytest
from pyproj import CRS, Transformer
from shapely.geometry import Polygon
from shapely.ops import transform

from app.geospatial.crs import (
    is_distorting_projection,
    is_usable_crs,
    project_for_measurement,
    utm_epsg_for,
)
from app.geospatial.errors import CrsError
from tests.helpers import geodesic_area, lonlat_square, shapefile_zip

WGS84 = CRS.from_epsg(4326)


@pytest.mark.parametrize(
    ("lon", "lat", "expected"),
    [
        (79.4, 13.6, 32644),  # India, northern hemisphere
        (151.2, -33.9, 32756),  # Sydney, southern hemisphere
        (-0.1, 51.5, 32630),  # London, zone west of Greenwich
        (180.0, 10.0, 32660),  # edge of the last zone
        (0.0, 85.0, 32661),  # UPS north
        (0.0, -85.0, 32761),  # UPS south
    ],
)
def test_utm_zone_selection(lon, lat, expected):
    assert utm_epsg_for(lon, lat) == expected


def test_epsg4326_is_transformed_so_area_is_metric_not_degrees():
    ring = lonlat_square(77.0, 12.0)
    polygon = Polygon(ring)

    projected = project_for_measurement(polygon, WGS84)

    assert polygon.area == pytest.approx(0.0001)  # the WRONG number: square degrees
    assert projected.crs_label == "EPSG:32643"
    assert projected.metres_per_unit == 1.0
    assert projected.geometry.area == pytest.approx(geodesic_area(ring), rel=0.005)


def test_southern_hemisphere_uses_south_utm_zone():
    projected = project_for_measurement(Polygon(lonlat_square(151.2, -33.9)), WGS84)

    assert projected.crs_label == "EPSG:32756"


def test_other_geographic_crs_is_handled():
    nad83 = CRS.from_epsg(4269)
    ring = lonlat_square(-100.0, 40.0)

    projected = project_for_measurement(Polygon(ring), nad83)

    assert projected.crs_label == "EPSG:32614"
    assert projected.geometry.area == pytest.approx(geodesic_area(ring), rel=0.005)


def test_suitable_projected_crs_is_used_directly():
    utm = CRS.from_epsg(32643)
    square = Polygon([(500000, 1400000), (500100, 1400000), (500100, 1400200), (500000, 1400200)])

    projected = project_for_measurement(square, utm)

    assert projected.crs_label == "EPSG:32643"
    assert projected.geometry is square
    assert projected.geometry.area == pytest.approx(20_000.0)


def test_projected_crs_in_feet_is_converted_to_metres():
    us_feet_crs = CRS.from_epsg(2278)  # NAD83 / Texas South Central (ftUS)
    square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])

    projected = project_for_measurement(square, us_feet_crs)

    assert projected.metres_per_unit == pytest.approx(0.3048006096)
    area_m2 = projected.geometry.area * projected.metres_per_unit**2
    assert area_m2 == pytest.approx(10_000 * 0.3048006096**2)


def test_web_mercator_is_not_trusted_and_is_reprojected_to_utm():
    ring = lonlat_square(25.0, 60.0)  # high latitude: Mercator inflates area ~4x
    web_mercator = CRS.from_epsg(3857)
    to_mercator = Transformer.from_crs(WGS84, web_mercator, always_xy=True)
    mercator_polygon = transform(to_mercator.transform, Polygon(ring))

    projected = project_for_measurement(mercator_polygon, web_mercator)

    assert is_distorting_projection(web_mercator)
    assert not is_distorting_projection(CRS.from_epsg(32643))
    assert mercator_polygon.area > 3 * geodesic_area(ring)  # naive result is badly wrong
    assert projected.crs_label == "EPSG:32635"
    assert projected.geometry.area == pytest.approx(geodesic_area(ring), rel=0.005)


def test_non_geodetic_crs_is_unusable():
    engineering = CRS.from_wkt(
        'LOCAL_CS["site grid",UNIT["metre",1],AXIS["x",EAST],AXIS["y",NORTH]]'
    )

    assert not is_usable_crs(engineering)
    with pytest.raises(CrsError):
        project_for_measurement(Polygon([(0, 0), (1, 0), (1, 1)]), engineering)


def test_coordinates_outside_geographic_range_raise():
    with pytest.raises(CrsError, match="outside the valid range"):
        project_for_measurement(Polygon([(500, 500), (501, 500), (501, 501)]), WGS84)


def _upload_polygon_zip(upload, gdf, prj_text=None):
    return upload("poly.zip", shapefile_zip(gdf, prj_text))


def test_missing_crs_extracts_features_but_never_measures(upload, client):
    gdf = gpd.GeoDataFrame(geometry=[Polygon([(0, 0), (10, 0), (10, 10)])], crs=None)

    uploaded = _upload_polygon_zip(upload, gdf)

    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["status"] == "FAILED"
    assert body["crs"] is None
    assert body["feature_count"] == 1
    assert "coordinate reference system" in body["error_message"]
    assert client.get(f"/api/files/{body['id']}/measurements/").status_code == 409
    features = client.get(f"/api/files/{body['id']}/features/").json()["features"]
    assert features[0]["geometry_type"] == "Polygon"


def test_invalid_prj_is_treated_as_missing_crs(upload):
    gdf = gpd.GeoDataFrame(geometry=[Polygon([(0, 0), (10, 0), (10, 10)])], crs="EPSG:32643")

    body = _upload_polygon_zip(upload, gdf, prj_text="this is not a CRS definition").json()

    assert body["status"] == "FAILED"
    assert body["crs"] is None
    assert "coordinate reference system" in body["error_message"]


def test_coordinates_not_matching_declared_geographic_crs_are_flagged_per_feature(upload, client):
    gdf = gpd.GeoDataFrame(
        geometry=[Polygon([(500000, 1400000), (500100, 1400000), (500100, 1400100)])],
        crs="EPSG:4326",  # wrong label: these are clearly projected metres
    )

    file_id = _upload_polygon_zip(upload, gdf).json()["id"]
    measurement = client.get(f"/api/files/{file_id}/measurements/").json()["measurements"][0]

    assert measurement["status"] == "INVALID"
    assert measurement["area"] is None
    assert "outside the valid range" in measurement["note"]
