"""Pydantic schemas for geospatial file upload, metadata, and measurements."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_serializer


class FileUploadResponse(BaseModel):
    """Response returned upon successful file upload and processing."""

    id: str = Field(..., description="Unique identifier for the processed geospatial file.", examples=["abc123"])
    filename: str = Field(..., description="Original filename uploaded by the user.", examples=["survey.kml"])
    feature_count: int = Field(..., description="Total number of geospatial features found.", examples=[120])
    crs: str = Field(..., description="Coordinate Reference System detected or inferred.", examples=["EPSG:4326"])
    status: str = Field(default="COMPLETED", description="Current processing status.", examples=["COMPLETED"])


class FileInfoResponse(BaseModel):
    """Response returned when fetching file information."""

    id: str = Field(..., description="Unique identifier for the file.", examples=["abc123"])
    filename: str = Field(..., description="Original filename uploaded by the user.", examples=["survey.kml"])
    feature_count: int = Field(..., description="Total number of geospatial features in the dataset.", examples=[120])
    crs: str = Field(..., description="Coordinate Reference System detected or inferred.", examples=["EPSG:4326"])
    status: str = Field(..., description="Processing status of the file.", examples=["COMPLETED"])


class FeatureMeasurement(BaseModel):
    """Measurement result for an individual geospatial feature."""

    feature_id: int = Field(..., description="Feature index/ID within the dataset.", examples=[0])
    geometry_type: str = Field(..., description="Geospatial geometry type.", examples=["Polygon"])
    area: Optional[float] = Field(default=None, description="Calculated area in square meters (for polygons).", examples=[12500.50])
    length: Optional[float] = Field(default=None, description="Calculated length in meters (for line strings).", examples=[850.25])
    unit: Optional[str] = Field(default=None, description="Metric measurement unit ('m²' or 'm').", examples=["m²"])
    measurement: Optional[float] = Field(default=None, description="Generic measurement value or null.")
    message: Optional[str] = Field(default=None, description="Reason if measurement cannot be computed.")
    properties: Optional[Dict[str, Any]] = Field(default=None, description="Feature attributes and properties.")

    @model_serializer(mode="wrap")
    def serialize_model(self, handler) -> Dict[str, Any]:
        """Custom serializer matching API specification requirements precisely."""
        data = handler(self)
        res: Dict[str, Any] = {
            "feature_id": data["feature_id"],
            "geometry_type": data["geometry_type"],
        }
        if data.get("area") is not None:
            res["area"] = data["area"]
        if data.get("length") is not None:
            res["length"] = data["length"]
        if data.get("unit") is not None:
            res["unit"] = data["unit"]

        # For Points or unmeasured types, include "measurement": null
        geom_type = data.get("geometry_type", "")
        if "Point" in geom_type or (data.get("area") is None and data.get("length") is None):
            res["measurement"] = data.get("measurement")

        if data.get("message") is not None:
            res["message"] = data["message"]
        if data.get("properties"):
            res["properties"] = data["properties"]

        return res


class MeasurementResponse(BaseModel):
    """Response returned when fetching measurement calculations for all features."""

    file_id: str = Field(..., description="Unique file ID.", examples=["abc123"])
    measurements: List[FeatureMeasurement] = Field(
        ...,
        description="List of measurements for all features in the file.",
    )
