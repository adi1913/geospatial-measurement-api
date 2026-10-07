"""Read KML files and zipped Shapefiles into a GeoDataFrame.

Both readers return a ``GeoDataFrame`` with 2D geometries, and raise
``FileReadError`` / ``InvalidArchiveError`` (with client-safe messages) when the
content cannot be used. The original library error is logged, not returned.
"""

import logging
import tempfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeElementTree
from pyogrio.errors import DataLayerError, DataSourceError

from app.geospatial.archive import ZipLimits, extract_shapefile
from app.geospatial.errors import FileReadError

logger = logging.getLogger(__name__)

_READ_ERRORS = (DataSourceError, DataLayerError, ValueError, UnicodeDecodeError)


def _drop_empty_property_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove property columns that are null for every feature (KML adds many)."""
    property_columns = [c for c in gdf.columns if c != gdf.geometry.name]
    empty = [c for c in property_columns if gdf[c].isna().all()]
    return gdf.drop(columns=empty)


def _force_2d(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop Z values; elevation is irrelevant for planimetric area and length."""
    gdf = gdf.copy()
    gdf[gdf.geometry.name] = shapely.force_2d(gdf.geometry.values)
    return gdf


def validate_kml_document(data: bytes) -> None:
    """Check that ``data`` is safe, well-formed XML whose root element is ``<kml>``.

    Parsing uses ``defusedxml`` with DTDs forbidden, so DOCTYPE declarations and
    entity tricks (XXE, "billion laughs") are rejected instead of being expanded.
    The namespace of the root element is ignored (KML 2.0, 2.1, 2.2 all work).
    Raises ``FileReadError`` with a client-safe message; parser details are only logged.
    """
    try:
        root = SafeElementTree.fromstring(data, forbid_dtd=True)
    except (DefusedXmlException, ParseError) as exc:
        logger.warning("Rejected KML upload (%s): %s", type(exc).__name__, exc)
        raise FileReadError("The file is not a valid KML document.") from exc

    if root.tag.rsplit("}", 1)[-1] != "kml":
        logger.warning("Rejected KML upload: root element is not <kml>")
        raise FileReadError("The file is not a valid KML document.")


def read_kml(path: Path) -> gpd.GeoDataFrame:
    """Read every layer (KML Folder) of a KML file into one GeoDataFrame."""
    try:
        layer_names = pyogrio.list_layers(path)[:, 0]
        layers = [gpd.read_file(path, layer=name) for name in layer_names]
    except _READ_ERRORS as exc:
        logger.warning("Could not read KML %s: %s", path.name, exc)
        raise FileReadError("The file could not be read as valid KML.") from exc

    layers = [layer for layer in layers if not layer.empty]
    if not layers:
        raise FileReadError("The KML file contains no features.")
    combined = gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), crs=layers[0].crs)
    return _drop_empty_property_columns(_force_2d(combined))


def read_shapefile_zip(path: Path, limits: ZipLimits) -> gpd.GeoDataFrame:
    """Safely extract a zipped Shapefile to a temp directory and read it."""
    with tempfile.TemporaryDirectory(prefix="shp_") as temp_dir:
        shp_path = extract_shapefile(path, Path(temp_dir), limits)
        try:
            gdf = gpd.read_file(shp_path)
        except _READ_ERRORS as exc:
            logger.warning("Could not read Shapefile from %s: %s", path.name, exc)
            raise FileReadError("The Shapefile could not be read.") from exc

    if gdf.empty:
        raise FileReadError("The Shapefile contains no features.")
    return _drop_empty_property_columns(_force_2d(gdf))


def read_geodata(path: Path, extension: str, limits: ZipLimits) -> gpd.GeoDataFrame:
    """Dispatch on the (already validated) file extension."""
    if extension == ".kml":
        return read_kml(path)
    if extension == ".zip":
        return read_shapefile_zip(path, limits)
    raise FileReadError("Unsupported file type.")
