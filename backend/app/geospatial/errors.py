"""Errors raised by the geospatial layer.

Messages on these exceptions are written to be safe to show to API clients:
they never contain file-system paths or library internals.
"""


class GeospatialError(Exception):
    """Base class for expected geospatial problems."""


class InvalidArchiveError(GeospatialError):
    """The ZIP is corrupt, unsafe, or does not contain a usable Shapefile."""


class FileReadError(GeospatialError):
    """The file passed validation but its content could not be read as geodata."""


class CrsError(GeospatialError):
    """A coordinate reference system is unusable for measuring."""
