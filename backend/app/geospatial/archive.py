"""Safe handling of ZIP archives that should contain one Shapefile.

Security rules enforced here:

* No member name may be absolute or contain ``..`` (ZIP Slip / path traversal).
* Symlinks and encrypted members are rejected.
* The number of entries and the *real* number of extracted bytes are capped
  (protection against ZIP bombs).
* Only the Shapefile components are extracted, and they are written under
  fixed names (``layer.shp`` ...) so no archive-supplied name is ever used
  as a file-system path.
"""

import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.geospatial.errors import InvalidArchiveError

REQUIRED_EXTENSIONS = (".shp", ".shx", ".dbf")
OPTIONAL_EXTENSIONS = (".prj", ".cpg")
_COPY_CHUNK = 64 * 1024


@dataclass(frozen=True)
class ZipLimits:
    """Upper bounds that protect against ZIP bombs."""

    max_entries: int
    max_uncompressed_bytes: int


def _check_member_name(name: str) -> PurePosixPath:
    """Reject names that could escape the extraction directory."""
    normalised = name.replace("\\", "/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or ".." in path.parts or (len(normalised) > 1 and normalised[1] == ":"):
        raise InvalidArchiveError("The ZIP archive contains an unsafe file path.")
    return path


def _check_member_flags(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise InvalidArchiveError("Encrypted ZIP archives are not supported.")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise InvalidArchiveError("The ZIP archive contains a symbolic link.")


def find_shapefile_members(
    archive: zipfile.ZipFile, limits: ZipLimits
) -> dict[str, zipfile.ZipInfo]:
    """Validate the archive and return ``{".shp": info, ".shx": info, ...}``.

    Exactly one Shapefile (same folder + same base name) must be present, with
    at least the ``.shp``, ``.shx`` and ``.dbf`` components.
    """
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > limits.max_entries:
        raise InvalidArchiveError("The ZIP archive contains too many files.")
    if sum(i.file_size for i in infos) > limits.max_uncompressed_bytes:
        raise InvalidArchiveError("The ZIP archive is too large when uncompressed.")

    groups: dict[tuple[str, str], dict[str, zipfile.ZipInfo]] = {}
    for info in infos:
        _check_member_flags(info)
        path = _check_member_name(info.filename)
        extension = path.suffix.lower()
        if extension in REQUIRED_EXTENSIONS + OPTIONAL_EXTENSIONS:
            key = (str(path.parent).lower(), path.stem.lower())
            groups.setdefault(key, {})[extension] = info

    shapefiles = {key: parts for key, parts in groups.items() if ".shp" in parts}
    if not shapefiles:
        raise InvalidArchiveError("The ZIP archive does not contain a .shp file.")
    if len(shapefiles) > 1:
        raise InvalidArchiveError("The ZIP archive must contain exactly one Shapefile.")

    members = next(iter(shapefiles.values()))
    missing = [ext for ext in REQUIRED_EXTENSIONS if ext not in members]
    if missing:
        raise InvalidArchiveError(
            "The Shapefile is incomplete; missing component(s): " + ", ".join(missing) + "."
        )
    return members


def open_archive(source: Path | BinaryIO) -> zipfile.ZipFile:
    """Open a ZIP (path or in-memory buffer), converting corruption into InvalidArchiveError."""
    try:
        return zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise InvalidArchiveError("The file is not a valid ZIP archive.") from exc


def validate_shapefile_zip(source: Path | BinaryIO, limits: ZipLimits) -> None:
    """Cheap structural check used at upload time, before anything is stored."""
    with open_archive(source) as archive:
        find_shapefile_members(archive, limits)


def _copy_limited(source, target, limit: int) -> int:
    """Copy ``source`` to ``target`` but stop with an error if more than ``limit`` bytes arrive."""
    written = 0
    while chunk := source.read(_COPY_CHUNK):
        written += len(chunk)
        if written > limit:
            raise InvalidArchiveError("The ZIP archive is too large when uncompressed.")
        target.write(chunk)
    return written


def extract_shapefile(zip_path: Path, destination: Path, limits: ZipLimits) -> Path:
    """Extract the Shapefile components into ``destination`` and return the ``.shp`` path."""
    with open_archive(zip_path) as archive:
        members = find_shapefile_members(archive, limits)
        remaining = limits.max_uncompressed_bytes
        for extension, info in members.items():
            target_path = destination / f"layer{extension}"
            try:
                with archive.open(info) as source, open(target_path, "wb") as target:
                    remaining -= _copy_limited(source, target, remaining)
            except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
                raise InvalidArchiveError("The ZIP archive is corrupt.") from exc
    return destination / "layer.shp"
