"""Builders that create small, realistic geodata on the fly (no binary fixtures)."""

import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from pyproj import Geod

GEOD = Geod(ellps="WGS84")


def lonlat_square(lon: float, lat: float, size: float = 0.01) -> list[tuple[float, float]]:
    """Closed ring of a square of ``size`` degrees whose lower-left corner is (lon, lat)."""
    return [
        (lon, lat),
        (lon + size, lat),
        (lon + size, lat + size),
        (lon, lat + size),
        (lon, lat),
    ]


def geodesic_area(ring: list[tuple[float, float]]) -> float:
    """Reference area (m²) computed on the WGS84 ellipsoid, independent of our UTM approach."""
    lons, lats = zip(*ring, strict=True)
    area, _ = GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def geodesic_length(line: list[tuple[float, float]]) -> float:
    lons, lats = zip(*line, strict=True)
    return GEOD.line_length(lons, lats)


def _coords(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x},{y},0" for x, y in points)


def polygon_xml(ring: list[tuple[float, float]]) -> str:
    return (
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        f"{_coords(ring)}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
    )


def line_xml(points: list[tuple[float, float]]) -> str:
    return f"<LineString><coordinates>{_coords(points)}</coordinates></LineString>"


def point_xml(point: tuple[float, float]) -> str:
    return f"<Point><coordinates>{_coords([point])}</coordinates></Point>"


def placemark(name: str, geometry_xml: str = "") -> str:
    return f"<Placemark><name>{name}</name>{geometry_xml}</Placemark>"


def kml_document(*placemarks: str) -> bytes:
    body = "".join(placemarks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        f"<Document><name>test</name>{body}</Document></kml>"
    ).encode()


def zip_bytes(members: dict[str, bytes]) -> bytes:
    """Build a ZIP from ``{name: content}`` without sanitising names (to craft bad archives)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def shapefile_members(gdf: gpd.GeoDataFrame, prj_text: str | None = None) -> dict[str, bytes]:
    """Write ``gdf`` as a Shapefile and return ``{"layer.shp": bytes, ...}``.

    The .prj is written by GeoPandas when ``gdf.crs`` is set. ``prj_text`` replaces it
    (used to simulate an invalid .prj).
    """
    with tempfile.TemporaryDirectory() as directory:
        gdf.to_file(Path(directory) / "layer.shp")
        members = {p.name: p.read_bytes() for p in Path(directory).iterdir()}
    if prj_text is not None:
        members["layer.prj"] = prj_text.encode()
    return members


def shapefile_zip(gdf: gpd.GeoDataFrame, prj_text: str | None = None) -> bytes:
    return zip_bytes(shapefile_members(gdf, prj_text))
