"""Persist per-feature results and turn them back into API responses."""

from app.db.models import FeatureRecord, FileRecord
from app.geospatial.processor import FeatureResult
from app.schemas.file import (
    FeatureItem,
    FeaturesResponse,
    MeasurementItem,
    MeasurementsResponse,
)

UNIT_AREA = "m²"
UNIT_LENGTH = "m"


def build_feature_records(file_id: str, features: list[FeatureResult]) -> list[FeatureRecord]:
    """Convert processor output into ORM rows."""
    return [
        FeatureRecord(
            file_id=file_id,
            feature_index=feature.index,
            geometry_type=feature.geometry_type,
            geometry=feature.geometry,
            properties=feature.properties,
            area_m2=feature.area_m2,
            length_m=feature.length_m,
            calculation_crs=feature.calculation_crs,
            status=feature.status.value,
            note=feature.note,
        )
        for feature in features
    ]


def _unit_for(feature: FeatureRecord) -> str | None:
    if feature.area_m2 is not None:
        return UNIT_AREA
    if feature.length_m is not None:
        return UNIT_LENGTH
    return None


def measurements_response(record: FileRecord) -> MeasurementsResponse:
    return MeasurementsResponse(
        file_id=record.id,
        crs=record.crs,
        measurements=[
            MeasurementItem(
                feature_id=f.feature_index,
                geometry_type=f.geometry_type,
                area=f.area_m2,
                length=f.length_m,
                unit=_unit_for(f),
                calculation_crs=f.calculation_crs,
                status=f.status,
                note=f.note,
            )
            for f in record.features
        ],
    )


def features_response(record: FileRecord) -> FeaturesResponse:
    return FeaturesResponse(
        file_id=record.id,
        crs=record.crs,
        features=[
            FeatureItem(
                feature_id=f.feature_index,
                geometry_type=f.geometry_type,
                geometry=f.geometry,
                properties=f.properties,
            )
            for f in record.features
        ],
    )
