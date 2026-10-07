"""Turn a geospatial file into structured, per-feature results.

The processor never raises because of a *single* bad feature: each feature
gets its own ``FeatureStatus`` and an explanatory note, so one unsupported or
invalid geometry cannot spoil the rest of the file. Only file-level problems
(unreadable file) raise, and a missing/unusable CRS is reported through
``ProcessingResult.error`` while the features are still extracted.
"""

import enum
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from app.geospatial.archive import ZipLimits
from app.geospatial.crs import describe_crs, is_usable_crs, project_for_measurement
from app.geospatial.errors import CrsError
from app.geospatial.reader import read_geodata

logger = logging.getLogger(__name__)

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
MEASUREMENT_DECIMALS = 4

MISSING_CRS_MESSAGE = (
    "No usable coordinate reference system (CRS) was found. For Shapefiles, include a valid "
    ".prj file. Features were extracted but no area or length was calculated, because "
    "measuring without a known CRS would give misleading results."
)
UNSUPPORTED_CRS_MESSAGE = (
    "The file's coordinate reference system is neither geographic nor projected, so area and "
    "length cannot be calculated. Features were extracted without measurements."
)


class FeatureStatus(enum.StrEnum):
    MEASURED = "MEASURED"  # area or length calculated
    NOT_APPLICABLE = "NOT_APPLICABLE"  # points: nothing to measure
    UNSUPPORTED = "UNSUPPORTED"  # geometry type we do not measure
    INVALID = "INVALID"  # missing/invalid geometry or unusable coordinates
    SKIPPED = "SKIPPED"  # not measured because the file has no usable CRS


@dataclass
class FeatureResult:
    index: int
    geometry_type: str | None
    geometry: dict | None
    properties: dict
    status: FeatureStatus
    area_m2: float | None = None
    length_m: float | None = None
    calculation_crs: str | None = None
    note: str | None = None


@dataclass
class ProcessingResult:
    crs: str | None
    features: list[FeatureResult] = field(default_factory=list)
    error: str | None = None


def _round(value: float) -> float:
    return round(value, MEASUREMENT_DECIMALS)


def _measure(geometry: BaseGeometry, crs: CRS, result: FeatureResult) -> None:
    """Fill in area or length on ``result`` using a metric CRS (never raw degrees)."""
    projected = project_for_measurement(geometry, crs)
    result.calculation_crs = projected.crs_label
    scale = projected.metres_per_unit
    if result.geometry_type in AREA_TYPES:
        result.area_m2 = _round(projected.geometry.area * scale**2)
    else:
        result.length_m = _round(projected.geometry.length * scale)
    result.status = FeatureStatus.MEASURED


def _process_feature(
    index: int,
    geometry: BaseGeometry | None,
    geojson: dict,
    crs: CRS | None,
) -> FeatureResult:
    """Classify, validate and (when possible) measure a single feature."""
    result = FeatureResult(
        index=index,
        geometry_type=geometry.geom_type if geometry is not None else None,
        geometry=geojson.get("geometry"),
        properties=geojson.get("properties") or {},
        status=FeatureStatus.INVALID,
    )
    if geometry is None or geometry.is_empty:
        result.note = "The feature has no geometry."
        return result

    gtype = result.geometry_type
    if gtype not in AREA_TYPES | LENGTH_TYPES | POINT_TYPES:
        result.status = FeatureStatus.UNSUPPORTED
        result.note = f"Geometry type '{gtype}' is not supported for measurement."
        return result

    if not geometry.is_valid:
        result.note = f"Invalid geometry: {explain_validity(geometry)}"
        return result

    if gtype in POINT_TYPES:
        result.status = FeatureStatus.NOT_APPLICABLE
        result.note = "Points have no area or length."
        return result

    if crs is None:
        result.status = FeatureStatus.SKIPPED
        result.note = "Not measured: the file has no usable CRS."
        return result

    try:
        _measure(geometry, crs, result)
    except CrsError as exc:
        result.note = str(exc)
    return result


def _file_crs_error(crs: CRS | None) -> str | None:
    if crs is None:
        return MISSING_CRS_MESSAGE
    if not is_usable_crs(crs):
        return UNSUPPORTED_CRS_MESSAGE
    return None


def process_file(path: Path, extension: str, limits: ZipLimits) -> ProcessingResult:
    """Read a stored upload and produce per-feature results.

    Raises ``GeospatialError`` subclasses for file-level problems.
    """
    gdf: gpd.GeoDataFrame = read_geodata(path, extension, limits)
    crs: CRS | None = gdf.crs
    error = _file_crs_error(crs)
    usable_crs = crs if error is None else None

    geojson_features = json.loads(gdf.to_json(drop_id=True))["features"]
    features = [
        _process_feature(index, geometry, geojson, usable_crs)
        for index, (geometry, geojson) in enumerate(
            zip(gdf.geometry, geojson_features, strict=True)
        )
    ]
    return ProcessingResult(
        crs=describe_crs(crs) if crs is not None else None,
        features=features,
        error=error,
    )
