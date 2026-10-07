"""Tests for file upload validation, processing, and file metadata retrieval."""

import io
from fastapi.testclient import TestClient


def test_upload_kml_success(client: TestClient, sample_kml_bytes: bytes):
    """Test successful upload and feature extraction from a valid .kml file."""
    files = {"file": ("survey.kml", io.BytesIO(sample_kml_bytes), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 201, response.text
    data = response.json()
    assert "id" in data
    assert data["filename"] == "survey.kml"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"


def test_upload_shapefile_zip_success(client: TestClient, valid_shapefile_zip_bytes: bytes):
    """Test successful upload and extraction from a valid Shapefile .zip archive."""
    files = {"file": ("parcels.zip", io.BytesIO(valid_shapefile_zip_bytes), "application/zip")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 201, response.text
    data = response.json()
    assert "id" in data
    assert data["filename"] == "parcels.zip"
    assert data["feature_count"] == 3
    assert data["status"] == "COMPLETED"
    assert "EPSG:4326" in data["crs"]


def test_upload_unsupported_file_extension(client: TestClient):
    """Test rejection when uploading an unsupported file format (e.g., .txt or .pdf)."""
    files = {"file": ("document.pdf", io.BytesIO(b"%PDF-1.4 dummy content"), "application/pdf")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 400
    assert "Unsupported file extension '.pdf'" in response.json()["detail"]


def test_upload_empty_file(client: TestClient):
    """Test rejection when uploading a 0-byte file."""
    files = {"file": ("empty.kml", io.BytesIO(b""), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_corrupted_kml(client: TestClient, corrupted_kml_bytes: bytes):
    """Test error handling when KML file has invalid or corrupted XML syntax."""
    files = {"file": ("corrupt.kml", io.BytesIO(corrupted_kml_bytes), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 422
    assert "malformed XML" in response.json()["detail"] or "Corrupted" in response.json()["detail"]


def test_upload_corrupted_zip(client: TestClient):
    """Test error handling when uploaded zip file is corrupted binary data."""
    files = {"file": ("bad.zip", io.BytesIO(b"PK\x03\x04not-a-valid-zip-data"), "application/zip")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 422
    assert "not a valid ZIP archive" in response.json()["detail"]


def test_upload_zip_without_shapefile(client: TestClient, zip_without_shapefile_bytes: bytes):
    """Test rejection when a ZIP archive does not contain any .shp file."""
    files = {"file": ("no_shp.zip", io.BytesIO(zip_without_shapefile_bytes), "application/zip")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 422
    assert "No .shp file found" in response.json()["detail"]


def test_upload_zip_missing_components(client: TestClient, incomplete_shapefile_zip_bytes: bytes):
    """Test rejection when a Shapefile archive lacks required companions (.shx)."""
    files = {"file": ("missing_shx.zip", io.BytesIO(incomplete_shapefile_zip_bytes), "application/zip")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 422
    assert "missing mandatory component" in response.json()["detail"].lower()
    assert ".shx" in response.json()["detail"]


def test_upload_zip_slip_security_defense(client: TestClient, zip_slip_attack_bytes: bytes):
    """Test security defense against directory traversal (Zip Slip) attacks."""
    files = {"file": ("exploit.zip", io.BytesIO(zip_slip_attack_bytes), "application/zip")}
    response = client.post("/api/files/", files=files)

    assert response.status_code == 422
    assert "traversal" in response.json()["detail"].lower() or "unsafe path" in response.json()["detail"].lower()


def test_get_file_info_success(client: TestClient, sample_kml_bytes: bytes):
    """Test retrieving file metadata via GET /api/files/{id}/."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("survey.kml", io.BytesIO(sample_kml_bytes), "application/vnd.google-earth.kml+xml")},
    )
    file_id = upload_res.json()["id"]

    info_res = client.get(f"/api/files/{file_id}/")
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["id"] == file_id
    assert info_data["filename"] == "survey.kml"
    assert info_data["feature_count"] == 3
    assert info_data["status"] == "COMPLETED"


def test_get_file_info_not_found(client: TestClient):
    """Test fetching nonexistent file ID returns HTTP 404."""
    response = client.get("/api/files/nonexistent_id_999/")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_endpoints_without_trailing_slash(client: TestClient, sample_kml_bytes: bytes):
    """Verify that endpoints work consistently without trailing slashes."""
    upload_res = client.post(
        "/api/files",
        files={"file": ("survey.kml", io.BytesIO(sample_kml_bytes), "application/vnd.google-earth.kml+xml")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    info_res = client.get(f"/api/files/{file_id}")
    assert info_res.status_code == 200

    meas_res = client.get(f"/api/files/{file_id}/measurements")
    assert meas_res.status_code == 200
    assert len(meas_res.json()["measurements"]) == 3
