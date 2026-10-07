"""Custom domain exceptions for the geospatial application."""


class GeospatialError(Exception):
    """Base exception for geospatial API errors."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RecordNotFoundError(GeospatialError):
    """Raised when a requested file record ID does not exist."""

    def __init__(self, file_id: str):
        super().__init__(f"File with ID '{file_id}' not found.", status_code=404)
        self.file_id = file_id


class InvalidFileFormatError(GeospatialError):
    """Raised when an uploaded file extension or mime type is unsupported."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class EmptyUploadError(GeospatialError):
    """Raised when an uploaded file is empty (0 bytes)."""

    def __init__(self, message: str = "Uploaded file is empty."):
        super().__init__(message, status_code=400)


class FileTooLargeError(GeospatialError):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, max_mb: int):
        super().__init__(f"Uploaded file exceeds maximum allowed size of {max_mb} MB.", status_code=413)


class CorruptedFileError(GeospatialError):
    """Raised when an uploaded KML or Shapefile is malformed or unreadable."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class ZipExtractionError(GeospatialError):
    """Raised when an archive contains security risks or cannot be parsed."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class MissingShapefileComponentError(GeospatialError):
    """Raised when a Shapefile archive is missing mandatory components (.shp, .shx, .dbf)."""

    def __init__(self, missing_components: list[str]):
        components_str = ", ".join(missing_components)
        super().__init__(
            f"Shapefile archive is missing mandatory component(s): {components_str}",
            status_code=422,
        )
        self.missing_components = missing_components


class CRSError(GeospatialError):
    """Raised when CRS cannot be resolved or projected."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)
