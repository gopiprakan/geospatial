"""File utility functions including security checks and archive handling."""

import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from app.exceptions import (
    EmptyUploadError,
    InvalidFileFormatError,
    MissingShapefileComponentError,
    ZipExtractionError,
)

ALLOWED_EXTENSIONS = {".kml", ".zip"}
REQUIRED_SHAPEFILE_EXTENSIONS = {".shp", ".shx", ".dbf"}


def generate_file_id() -> str:
    """Generate a unique, clean alphanumeric file identifier."""
    return uuid.uuid4().hex[:12]


def validate_file_extension(filename: Optional[str]) -> str:
    """
    Validate that the uploaded file has an allowed extension (.kml or .zip).

    Returns:
        The normalized lowercase extension (e.g., '.kml' or '.zip').
    """
    if not filename:
        raise InvalidFileFormatError("Filename cannot be empty.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise InvalidFileFormatError(
            f"Unsupported file extension '{ext}'. Allowed extensions are: {allowed_str}"
        )
    return ext


def safe_extract_zip(zip_path: Path, extract_to: Path) -> List[Path]:
    """
    Safely extract a ZIP archive while preventing Zip Slip path traversal attacks.

    Args:
        zip_path: Path to the .zip archive file.
        extract_to: Destination directory for extracted files.

    Returns:
        List of paths to extracted files.
    """
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        raise EmptyUploadError("Uploaded ZIP file is empty or does not exist.")

    extract_to = extract_to.resolve()
    extract_to.mkdir(parents=True, exist_ok=True)
    extracted_paths: List[Path] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            # Check for bad or corrupted zip
            test_bad = archive.testzip()
            if test_bad:
                raise ZipExtractionError(f"Corrupted file inside ZIP archive: {test_bad}")

            for member in archive.infolist():
                # Security: Check for path traversal attacks
                target_path = (extract_to / member.filename).resolve()

                # Ensure target path stays strictly inside destination directory
                try:
                    target_path.relative_to(extract_to)
                except ValueError:
                    raise ZipExtractionError(
                        f"Attempted path traversal (Zip Slip) detected for member: {member.filename}"
                    )

                if ".." in member.filename or member.filename.startswith(("/", "\\")):
                    raise ZipExtractionError(
                        f"Unsafe path detected in ZIP archive: {member.filename}"
                    )

                # Extract directory or file
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    extracted_paths.append(target_path)

    except zipfile.BadZipFile as e:
        raise ZipExtractionError(f"Uploaded file is not a valid ZIP archive: {str(e)}")

    return extracted_paths


def verify_shapefile_components(extracted_dir: Path) -> Tuple[Path, str]:
    """
    Verify that the extracted folder contains a valid Shapefile with required components:
    .shp, .shx, and .dbf with matching basenames.

    Returns:
        Tuple of (Path to main .shp file, base name).
    """
    all_files = [p for p in extracted_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]

    shp_files = [p for p in all_files if p.suffix.lower() == ".shp"]

    if not shp_files:
        raise ZipExtractionError("No .shp file found in uploaded ZIP archive.")

    # Locate the primary shapefile
    shp_file = shp_files[0]
    base_stem = shp_file.stem
    parent_dir = shp_file.parent

    # Check for required companions
    missing: List[str] = []
    for ext in REQUIRED_SHAPEFILE_EXTENSIONS:
        expected = parent_dir / f"{base_stem}{ext}"
        # Case-insensitive match in parent directory
        match = any(p.suffix.lower() == ext and p.stem.lower() == base_stem.lower() for p in parent_dir.iterdir() if p.is_file())
        if not match:
            missing.append(ext)

    if missing:
        raise MissingShapefileComponentError(missing)

    return shp_file, base_stem


def cleanup_path(path: Path) -> None:
    """Safely remove a file or directory tree if it exists."""
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
    except Exception:
        pass
