"""Upload security: ZIP Slip, incomplete Shapefiles, ZIP bombs, filename handling."""

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.geospatial.archive import ZipLimits, find_shapefile_members
from app.geospatial.errors import InvalidArchiveError
from app.geospatial.reader import read_shapefile_zip
from app.services.file_service import sanitize_filename
from tests.helpers import (
    kml_document,
    lonlat_square,
    placemark,
    polygon_xml,
    shapefile_members,
    zip_bytes,
)

LIMITS = ZipLimits(max_entries=100, max_uncompressed_bytes=10 * 1024 * 1024)
GDF = gpd.GeoDataFrame({"n": [1]}, geometry=[Point(500000, 1400000)], crs="EPSG:32643")


@pytest.fixture
def members() -> dict[str, bytes]:
    return shapefile_members(GDF)


@pytest.mark.parametrize(
    "malicious_name",
    ["../evil.shp", "..\\evil.shp", "/etc/evil.shp", "C:\\evil.shp", "a/../../evil.shp"],
)
def test_zip_slip_member_names_are_rejected(upload, tmp_path, members, malicious_name):
    members[malicious_name] = b"x"

    response = upload("slip.zip", zip_bytes(members))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"
    assert "unsafe" in response.json()["error"]["message"]
    assert not list(tmp_path.parent.glob("evil*"))
    assert not list(tmp_path.glob("**/evil*"))


@pytest.mark.parametrize("missing", ["layer.shx", "layer.dbf", "layer.shp"])
def test_incomplete_shapefile_is_rejected(upload, members, missing):
    del members[missing]

    response = upload("partial.zip", zip_bytes(members))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"


def test_missing_component_is_named_in_message(upload, members):
    del members["layer.shx"]

    message = upload("partial.zip", zip_bytes(members)).json()["error"]["message"]

    assert ".shx" in message


def test_zip_without_any_shapefile_is_rejected(upload):
    response = upload("docs.zip", zip_bytes({"readme.txt": b"hello"}))

    assert response.status_code == 400
    assert ".shp" in response.json()["error"]["message"]


def test_zip_with_two_shapefiles_is_rejected(upload, members):
    second = {f"other{name[len('layer') :]}": data for name, data in members.items()}

    response = upload("two.zip", zip_bytes({**members, **second}))

    assert response.status_code == 400
    assert "exactly one Shapefile" in response.json()["error"]["message"]


def test_zip_bomb_by_declared_size_is_rejected(upload, settings, members):
    settings.max_zip_uncompressed_mb = 1
    members["padding.txt"] = b"\0" * (3 * 1024 * 1024)  # compresses to a few KB

    response = upload("bomb.zip", zip_bytes(members))

    assert response.status_code == 400
    assert "too large when uncompressed" in response.json()["error"]["message"]


def test_zip_with_too_many_entries_is_rejected(upload, settings, members):
    settings.max_zip_entries = 10
    members.update({f"extra{i}.txt": b"x" for i in range(20)})

    response = upload("many.zip", zip_bytes(members))

    assert response.status_code == 400
    assert "too many files" in response.json()["error"]["message"]


def test_symlink_member_is_rejected(tmp_path, members):
    path = tmp_path / "link.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        link = zipfile.ZipInfo("link.txt")
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "/etc/passwd")

    with zipfile.ZipFile(path) as archive, pytest.raises(InvalidArchiveError, match="symbolic"):
        find_shapefile_members(archive, LIMITS)


def test_shapefile_inside_a_folder_and_with_upper_case_extensions_is_accepted(tmp_path, members):
    nested = {f"data/LAYER{Path(n).suffix.upper()}": d for n, d in members.items()}
    path = tmp_path / "nested.zip"
    path.write_bytes(zip_bytes(nested))

    gdf = read_shapefile_zip(path, LIMITS)

    assert len(gdf) == 1


def test_extraction_directory_is_cleaned_up(tmp_path, members, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    path = tmp_path / "ok.zip"
    path.write_bytes(zip_bytes(members))

    read_shapefile_zip(path, LIMITS)

    assert list(scratch.iterdir()) == []


def test_archive_names_never_become_file_system_paths(tmp_path, members, monkeypatch):
    """Files are extracted under fixed names, so even odd archive names cannot escape."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    seen: list[str] = []
    original = zipfile.ZipFile.open

    def spy(self, info, *args, **kwargs):
        seen.append(str(info.filename))
        return original(self, info, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    path = tmp_path / "weird.zip"
    path.write_bytes(zip_bytes({f"deep/folder/{n}": d for n, d in members.items()}))

    read_shapefile_zip(path, LIMITS)

    assert seen and all(name.startswith("deep/folder/") for name in seen)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("survey.kml", "survey.kml"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\boot.ini", "boot.ini"),
        ("bad\x00name\n.kml", "badname.kml"),
        ("", "upload"),
        (None, "upload"),
        ("a" * 400 + ".kml", ("a" * 400 + ".kml")[:255]),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


# --- KML XML validation (defusedxml) ---------------------------------------------------------

PLOT = placemark("plot", polygon_xml(lonlat_square(77.0, 12.0)))
KML_NS_21 = "http://earth.google.com/kml/2.1"
INVALID_KML_MESSAGE = "The file is not a valid KML document."
PARSER_LEAK_MARKERS = ["defusedxml", "ParseError", "Entities", "DTD", "line ", "column", "expat"]


def assert_rejected_as_invalid_kml(response):
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "INVALID_FILE_CONTENT", "message": INVALID_KML_MESSAGE}
    }
    for marker in PARSER_LEAK_MARKERS:
        assert marker not in response.text


def test_valid_namespaced_kml_is_accepted(upload):
    response = upload("ns.kml", kml_document(PLOT))

    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"


def test_valid_kml_with_other_namespace_or_none_is_accepted(upload):
    older = f'<kml xmlns="{KML_NS_21}"><Document>{PLOT}</Document></kml>'.encode()
    plain = f"<kml><Document>{PLOT}</Document></kml>".encode()

    assert upload("older.kml", older).json()["status"] == "COMPLETED"
    assert upload("plain.kml", plain).json()["status"] == "COMPLETED"


def test_valid_kml_with_xml_declaration_and_bom_is_accepted(upload):
    with_bom = b"\xef\xbb\xbf" + kml_document(PLOT)

    assert upload("bom.kml", with_bom).status_code == 201


@pytest.mark.parametrize(
    "broken",
    [
        kml_document(PLOT)[:-30],  # truncated
        b"<kml><Document><Placemark></Document></kml>",  # mismatched tags
        b"<kml><Document>& unescaped ampersand</Document></kml>",
        b"<kml>" + b"\xff\xfe not text",
        b"<?xml version='1.0'?>",  # no root element
    ],
    ids=["truncated", "mismatched-tags", "bad-ampersand", "bad-bytes", "no-root"],
)
def test_malformed_xml_is_rejected(upload, settings, broken):
    response = upload("broken.kml", broken)

    assert_rejected_as_invalid_kml(response)
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


BILLION_LAUGHS = (
    b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "aaaaaaaaaa">'
    b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
    b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
    b"<kml><Document><name>&c;</name></Document></kml>"
)
XXE_FILE = (
    b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    b"<kml><Document><name>&xxe;</name></Document></kml>"
)
HARMLESS_DOCTYPE = b'<?xml version="1.0"?><!DOCTYPE kml><kml><Document/></kml>'


@pytest.mark.parametrize(
    "payload",
    [BILLION_LAUGHS, XXE_FILE, HARMLESS_DOCTYPE],
    ids=["billion-laughs", "external-entity", "any-doctype"],
)
def test_doctype_and_entity_payloads_are_rejected(upload, settings, payload):
    response = upload("evil.kml", payload)

    assert_rejected_as_invalid_kml(response)
    assert "root:" not in response.text  # nothing from /etc/passwd
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


@pytest.mark.parametrize(
    "document",
    [
        b"<gpx><trk/></gpx>",
        b"<html><body>not kml</body></html>",
        b"<kmlish><Document/></kmlish>",
        b"<wrapper><kml><Document/></kml></wrapper>",
        b'<other xmlns="http://www.opengis.net/kml/2.2"><Document/></other>',
    ],
    ids=["gpx", "html", "similar-name", "kml-not-root", "kml-namespace-wrong-root"],
)
def test_wrong_root_element_is_rejected(upload, document):
    assert_rejected_as_invalid_kml(upload("wrong.kml", document))


def test_string_containing_kml_text_is_not_enough(upload):
    """Old string sniffing would have accepted this: '<kml' appears, but it is not XML."""
    response = upload("sneaky.kml", b"<kml <<< this is not well-formed XML <kml>")

    assert_rejected_as_invalid_kml(response)
