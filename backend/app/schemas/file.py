"""Pydantic models describing what the API returns."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_serializer

from app.db.models import FileStatus
from app.geospatial.processor import FeatureStatus


class FileResponse(BaseModel):
    """Metadata of an uploaded file. ``error_message`` appears only for FAILED files."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None = None
    status: FileStatus
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        """SQLite returns naive datetimes; everything is stored in UTC."""
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @model_serializer(mode="wrap")
    def _omit_empty_error(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if data.get("error_message") is None:
            data.pop("error_message", None)
        return data


class MeasurementItem(BaseModel):
    """Measurement of one feature. ``area`` is in m², ``length`` in m."""

    feature_id: int
    geometry_type: str | None
    area: float | None = None
    length: float | None = None
    unit: str | None = None
    calculation_crs: str | None = None
    status: FeatureStatus
    note: str | None = None


class MeasurementsResponse(BaseModel):
    file_id: str
    crs: str | None
    measurements: list[MeasurementItem]


class FeatureItem(BaseModel):
    """A feature as extracted from the file (geometry is GeoJSON in the file's CRS)."""

    feature_id: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class FeaturesResponse(BaseModel):
    file_id: str
    crs: str | None
    features: list[FeatureItem]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
