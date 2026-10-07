"""CRS detection and selection of a metric CRS for measuring.

Why this module exists
----------------------
Shapely computes ``area`` and ``length`` in the *units of the coordinates*.
For EPSG:4326 those units are degrees, so ``polygon.area`` would be a number
of "square degrees", which is meaningless and varies with latitude. We must
therefore measure in a projected CRS whose unit is a length.

Strategy (applied to every feature)
-----------------------------------
1. **Projected source CRS that is suitable** (e.g. UTM, a national grid, State
   Plane): measure directly in it. If its unit is not the metre (e.g. US survey
   foot) the result is converted with the unit's metre factor.
2. **Geographic source CRS** (EPSG:4326, NAD83, any lat/lon CRS): take the
   centre of the feature's bounding box, convert it to WGS84 lon/lat, pick the
   UTM zone containing it (north/south by latitude; UPS polar stereographic
   beyond 84°N / 80°S), and transform the geometry into that zone.
3. **Projected but distorting CRS** (Web Mercator and other Mercator
   variants): area is inflated away from the equator, so the geometry is
   treated like case 2: converted back to lon/lat and re-projected to UTM.
4. **Missing or non-geodetic CRS**: no measurement is made (see processor).

Known limitation: a single feature spanning several UTM zones (or crossing the
antimeridian) is measured in the zone of its centre, so it loses some accuracy.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.geospatial.errors import CrsError

WGS84 = CRS.from_epsg(4326)
UTM_NORTH_BASE = 32600
UTM_SOUTH_BASE = 32700
UPS_NORTH_EPSG = 32661
UPS_SOUTH_EPSG = 32761
UTM_MAX_LATITUDE = 84.0
UTM_MIN_LATITUDE = -80.0


@dataclass(frozen=True)
class ProjectedGeometry:
    """A geometry ready for measuring, plus how to turn its units into metres."""

    geometry: BaseGeometry
    crs_label: str
    metres_per_unit: float


def describe_crs(crs: CRS) -> str:
    """Return ``EPSG:xxxx`` when the CRS matches an authority code, else its name."""
    authority = crs.to_authority(min_confidence=70)
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return crs.name


def is_usable_crs(crs: CRS) -> bool:
    """Only geographic or projected CRSs can be used for planimetric measuring."""
    return bool(crs.is_geographic or crs.is_projected)


def is_distorting_projection(crs: CRS) -> bool:
    """True for Mercator-family projections (not Transverse/Oblique Mercator).

    Their area/length scale grows quickly away from the equator, so they are
    unsuitable for measuring even though their unit is the metre.
    """
    if not crs.is_projected or crs.coordinate_operation is None:
        return False
    method = crs.coordinate_operation.method_name.lower()
    return "mercator" in method and "transverse" not in method and "oblique" not in method


def utm_epsg_for(longitude: float, latitude: float) -> int:
    """EPSG code of the UTM zone (or UPS polar zone) containing a lon/lat point."""
    if latitude >= UTM_MAX_LATITUDE:
        return UPS_NORTH_EPSG
    if latitude < UTM_MIN_LATITUDE:
        return UPS_SOUTH_EPSG
    zone = min(int((longitude + 180.0) // 6.0) + 1, 60)
    base = UTM_NORTH_BASE if latitude >= 0 else UTM_SOUTH_BASE
    return base + zone


@lru_cache(maxsize=128)
def _transformer(source: CRS, target: CRS) -> Transformer:
    """Cached transformer; ``always_xy`` keeps (lon, lat) / (x, y) order everywhere."""
    return Transformer.from_crs(source, target, always_xy=True)


def _metres_per_unit(crs: CRS) -> float:
    """Metres per coordinate unit of a projected CRS (1.0 for metre-based CRSs)."""
    factor = crs.axis_info[0].unit_conversion_factor
    if not factor or not math.isfinite(factor) or factor <= 0:
        raise CrsError("The projected CRS has an unknown linear unit.")
    return float(factor)


def _centre_lon_lat(geometry: BaseGeometry, source: CRS) -> tuple[float, float]:
    """Centre of the geometry's bounding box, expressed as WGS84 lon/lat."""
    min_x, min_y, max_x, max_y = geometry.bounds
    lon, lat = _transformer(source, WGS84).transform((min_x + max_x) / 2, (min_y + max_y) / 2)
    if not (math.isfinite(lon) and math.isfinite(lat)) or abs(lon) > 180 or abs(lat) > 90:
        raise CrsError("Coordinates are outside the valid range for the file's CRS.")
    return lon, lat


def project_for_measurement(geometry: BaseGeometry, source: CRS) -> ProjectedGeometry:
    """Return the geometry in a CRS where area/length are meaningful (see module docstring)."""
    if not is_usable_crs(source):
        raise CrsError("The file's CRS is neither geographic nor projected.")

    if source.is_projected and not is_distorting_projection(source):
        return ProjectedGeometry(geometry, describe_crs(source), _metres_per_unit(source))

    lon, lat = _centre_lon_lat(geometry, source)
    target = CRS.from_epsg(utm_epsg_for(lon, lat))
    projected = transform(_transformer(source, target).transform, geometry)
    if not all(math.isfinite(v) for v in projected.bounds):
        raise CrsError("The geometry could not be transformed to a metric CRS.")
    return ProjectedGeometry(projected, describe_crs(target), 1.0)
