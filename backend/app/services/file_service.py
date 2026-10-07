"""Upload handling: validate -> store safely -> process -> save results."""

import io
import logging
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import FileRecord, FileStatus
from app.geospatial.archive import ZipLimits, validate_shapefile_zip
from app.geospatial.errors import FileReadError, GeospatialError, InvalidArchiveError
from app.geospatial.processor import ProcessingResult, process_file
from app.geospatial.reader import validate_kml_document
from app.services.measurement_service import build_feature_records

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".kml", ".zip"}
ZIP_SIGNATURE = b"PK\x03\x04"
READ_CHUNK = 1024 * 1024
MAX_DISPLAY_NAME_LENGTH = 255
INTERNAL_FAILURE_MESSAGE = "The file could not be processed because of an internal error."


def sanitize_filename(raw_name: str | None) -> str:
    """Make a client-supplied name safe to *display* (it is never used as a path)."""
    name = re.split(r"[\\/]", raw_name or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:MAX_DISPLAY_NAME_LENGTH] or "upload"


def get_extension(filename: str) -> str:
    """Return the lower-case extension or reject the upload."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "Only .kml and .zip files are accepted.")
    return extension


def read_with_limit(upload: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in chunks and stop as soon as it exceeds the size limit."""
    chunks: list[bytes] = []
    total = 0
    while chunk := upload.file.read(READ_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                413,
                "FILE_TOO_LARGE",
                f"The file exceeds the maximum size of {max_bytes // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    if total == 0:
        raise AppError(400, "EMPTY_FILE", "The uploaded file is empty.")
    return b"".join(chunks)


def validate_content(data: bytes, extension: str, limits: ZipLimits) -> None:
    """Check the real content, not just the extension."""
    if extension == ".zip":
        if not data.startswith(ZIP_SIGNATURE):
            raise AppError(400, "INVALID_FILE_CONTENT", "The file is not a valid ZIP archive.")
        try:
            validate_shapefile_zip(io.BytesIO(data), limits)
        except InvalidArchiveError as exc:
            raise AppError(400, "INVALID_ARCHIVE", str(exc)) from exc
    else:
        try:
            validate_kml_document(data)
        except FileReadError as exc:
            raise AppError(400, "INVALID_FILE_CONTENT", str(exc)) from exc


def _store_file(data: bytes, stored_path: Path) -> None:
    """Write the upload under a server-generated name; ``xb`` refuses to overwrite."""
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stored_path, "xb") as target:
        target.write(data)


def _apply_result(record: FileRecord, result: ProcessingResult) -> None:
    record.crs = result.crs
    record.features = build_feature_records(record.id, result.features)
    record.feature_count = len(result.features)
    record.error_message = result.error
    record.status = FileStatus.FAILED.value if result.error else FileStatus.COMPLETED.value


def _mark_failed(record: FileRecord, message: str) -> None:
    record.status = FileStatus.FAILED.value
    record.error_message = message


def _run_processing(record: FileRecord, stored_path: Path, limits: ZipLimits) -> None:
    """Process the stored file and record the outcome; never lets an exception escape."""
    try:
        result = process_file(stored_path, record.original_extension, limits)
    except GeospatialError as exc:
        logger.warning("Processing failed for file %s: %s", record.id, exc)
        _mark_failed(record, str(exc))
    except Exception:
        logger.exception("Unexpected error while processing file %s", record.id)
        _mark_failed(record, INTERNAL_FAILURE_MESSAGE)
    else:
        _apply_result(record, result)


def upload_file(db: Session, upload: UploadFile, settings: Settings) -> FileRecord:
    """Validate and store an upload, process it synchronously, and return its record."""
    display_name = sanitize_filename(upload.filename)
    extension = get_extension(display_name)
    limits = ZipLimits(settings.max_zip_entries, settings.max_zip_uncompressed_bytes)

    data = read_with_limit(upload, settings.max_upload_bytes)
    validate_content(data, extension, limits)

    file_id = uuid.uuid4().hex
    stored_filename = f"{file_id}{extension}"
    stored_path = settings.upload_dir / stored_filename
    _store_file(data, stored_path)

    record = FileRecord(
        id=file_id,
        filename=display_name,
        stored_filename=stored_filename,
        original_extension=extension,
        status=FileStatus.PROCESSING.value,
    )
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    _run_processing(record, stored_path, limits)
    db.commit()
    return record


def get_file_or_404(db: Session, file_id: str) -> FileRecord:
    record = db.get(FileRecord, file_id)
    if record is None:
        raise AppError(404, "FILE_NOT_FOUND", "No file exists with this id.")
    return record
