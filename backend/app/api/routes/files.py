"""HTTP layer only: parse the request, call a service, shape the response."""

from fastapi import APIRouter, Depends, File, Header, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.database import get_db
from app.db.models import FileStatus
from app.schemas.file import (
    ErrorResponse,
    FeaturesResponse,
    FileResponse,
    MeasurementsResponse,
)
from app.services import file_service, measurement_service

router = APIRouter(prefix="/api/files", tags=["files"])

# Multipart framing adds a little overhead on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid input"},
    404: {"model": ErrorResponse, "description": "File not found"},
    413: {"model": ErrorResponse, "description": "File too large"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
}


@router.post(
    "/",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={code: ERROR_RESPONSES[code] for code in (400, 413, 422, 500)},
    summary="Upload a .kml or zipped Shapefile",
)
def upload_file(
    file: UploadFile = File(..., description="A .kml file or a .zip containing one Shapefile"),
    content_length: int | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Validate, store and process the file synchronously.

    A file that is accepted always gets an id. If its *content* cannot be
    processed (corrupt data, missing CRS) the response still has HTTP 201 but
    `status` is `FAILED` and `error_message` explains why.
    """
    if (
        content_length is not None
        and content_length > settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
    ):
        raise AppError(413, "FILE_TOO_LARGE", "The file exceeds the maximum allowed size.")
    record = file_service.upload_file(db, file, settings)
    return FileResponse.model_validate(record)


@router.get(
    "/{file_id}/",
    response_model=FileResponse,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get file metadata and processing status",
)
def get_file(file_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return FileResponse.model_validate(file_service.get_file_or_404(db, file_id))


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    responses={
        404: ERROR_RESPONSES[404],
        409: {"model": ErrorResponse, "description": "Not available"},
    },
    summary="Get area/length measurements for every feature",
)
def get_measurements(file_id: str, db: Session = Depends(get_db)) -> MeasurementsResponse:
    """Area in m² for polygons, length in m for lines. Points have no measurement."""
    record = file_service.get_file_or_404(db, file_id)
    if record.status == FileStatus.FAILED.value:
        raise AppError(
            409, "MEASUREMENTS_UNAVAILABLE", f"Processing failed: {record.error_message}"
        )
    if record.status != FileStatus.COMPLETED.value:
        raise AppError(409, "FILE_NOT_READY", "The file is still being processed.")
    return measurement_service.measurements_response(record)


@router.get(
    "/{file_id}/features/",
    response_model=FeaturesResponse,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get extracted features (geometry and properties)",
)
def get_features(file_id: str, db: Session = Depends(get_db)) -> FeaturesResponse:
    """Geometries are GeoJSON in the file's own CRS. Also available for FAILED files
    when features could be extracted (for example when the CRS is missing)."""
    return measurement_service.features_response(file_service.get_file_or_404(db, file_id))
