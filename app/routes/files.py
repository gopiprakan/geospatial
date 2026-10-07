"""FastAPI endpoints for geospatial file upload, inspection, and measurements."""

import logging
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import settings
from app.exceptions import (
    EmptyUploadError,
    FileTooLargeError,
    RecordNotFoundError,
)
from app.schemas.error import ErrorResponse
from app.schemas.file import (
    FileInfoResponse,
    FileUploadResponse,
    MeasurementResponse,
)
from app.services.file_processor import file_processor_service
from app.services.measurement import measurement_service
from app.services.storage import storage_service
from app.utils.file_utils import (
    cleanup_path,
    generate_file_id,
    validate_file_extension,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/files",
    tags=["Files & Measurements"],
)


@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a geospatial file (.kml or Shapefile .zip)",
    description=(
        "Accepts a multipart file upload (.kml or .zip containing a Shapefile), "
        "validates geometry and CRS, computes measurements, and stores metadata."
    ),
    responses={
        201: {"description": "File successfully uploaded and processed.", "model": FileUploadResponse},
        400: {"description": "Invalid file format, empty upload, or validation error.", "model": ErrorResponse},
        413: {"description": "File exceeds upload size limit.", "model": ErrorResponse},
        422: {"description": "Corrupted file, missing Shapefile components, or processing error.", "model": ErrorResponse},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="Geospatial file (.kml or Shapefile .zip)"),
) -> FileUploadResponse:
    """Handle multipart file upload, parse features, compute measurements, and persist."""
    # 1. Validate file extension
    original_filename = file.filename or "unknown"
    ext = validate_file_extension(original_filename)

    # 2. Generate unique file ID
    file_id = generate_file_id()
    temp_save_path = settings.upload_dir / f"{file_id}{ext}"

    try:
        # Read file chunks and enforce size limits
        total_bytes = 0
        max_bytes = settings.max_upload_size_mb * 1024 * 1024

        with open(temp_save_path, "wb") as f_out:
            while chunk := await file.read(1024 * 64):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLargeError(settings.max_upload_size_mb)
                f_out.write(chunk)

        if total_bytes == 0:
            raise EmptyUploadError("Uploaded file is empty (0 bytes).")

        # 3. Process the file into GeoDataFrame
        gdf, crs_str = file_processor_service.process_file(temp_save_path, original_filename)

        # 4. Calculate feature measurements
        measurements = measurement_service.measure_geodataframe(gdf)

        # 5. Persist record in database
        saved_record = storage_service.save_file_record(
            file_id=file_id,
            filename=original_filename,
            feature_count=len(gdf),
            crs=crs_str,
            status="COMPLETED",
            measurements=measurements,
        )

        return FileUploadResponse(**saved_record)

    except Exception:
        # Clean up temporary uploaded file on failure
        cleanup_path(temp_save_path)
        raise
    finally:
        await file.close()


@router.get(
    "/{id}/",
    response_model=FileInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get file information and metadata",
    description="Retrieve processing status, feature count, CRS, and original filename for a file ID.",
    responses={
        200: {"description": "File metadata details.", "model": FileInfoResponse},
        404: {"description": "File ID not found.", "model": ErrorResponse},
    },
)
def get_file_info(id: str) -> FileInfoResponse:
    """Retrieve file metadata by unique ID."""
    record = storage_service.get_file_record(id)
    return FileInfoResponse(**record)


@router.get(
    "/{id}/measurements/",
    response_model=MeasurementResponse,
    status_code=status.HTTP_200_OK,
    summary="Get feature measurements",
    description=(
        "Retrieve metric measurements for every feature in the file. "
        "Polygons return area (m²), LineStrings return length (m), Points return measurement: null."
    ),
    responses={
        200: {"description": "List of feature measurements.", "model": MeasurementResponse},
        404: {"description": "File ID not found.", "model": ErrorResponse},
    },
)
def get_file_measurements(id: str) -> MeasurementResponse:
    """Retrieve measurements for all features in the file."""
    # Ensure file exists
    storage_service.get_file_record(id)
    measurements = storage_service.get_measurements(id)
    return MeasurementResponse(file_id=id, measurements=measurements)
