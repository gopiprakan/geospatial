"""Tests for geospatial measurement calculations, units, and unsupported geometries."""

import io
from fastapi.testclient import TestClient
import pyproj
from shapely.geometry import (
    GeometryCollection,
    LineString,
    Point,
    Polygon,
)

from app.services.measurement import measurement_service


def test_measurements_from_kml_upload(client: TestClient, sample_kml_bytes: bytes):
    """Test measurements endpoint returns correct types, units, and values for KML features."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("survey.kml", io.BytesIO(sample_kml_bytes), "application/vnd.google-earth.kml+xml")},
    )
    file_id = upload_res.json()["id"]

    meas_res = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_res.status_code == 200
    data = meas_res.json()
    assert data["file_id"] == file_id
    measurements = data["measurements"]
    assert len(measurements) == 3

    # Feature 0: Polygon
    poly_m = next(m for m in measurements if m["geometry_type"] == "Polygon")
    assert poly_m["area"] is not None
    assert poly_m["area"] > 10000.0  # Approx 1.2 sq km (1.2 million m²)
    assert poly_m["unit"] == "m²"
    assert "length" not in poly_m or poly_m["length"] is None

    # Feature 1: LineString
    line_m = next(m for m in measurements if m["geometry_type"] == "LineString")
    assert line_m["length"] is not None
    assert line_m["length"] > 1000.0  # Approx 1.5 km
    assert line_m["unit"] == "m"
    assert "area" not in line_m or line_m["area"] is None

    # Feature 2: Point
    point_m = next(m for m in measurements if m["geometry_type"] == "Point")
    assert point_m["measurement"] is None
    assert "area" not in point_m or point_m["area"] is None
    assert "length" not in point_m or point_m["length"] is None


def test_measurements_from_shapefile_upload(client: TestClient, valid_shapefile_zip_bytes: bytes):
    """Test measurements endpoint with shapefile upload."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("parcels.zip", io.BytesIO(valid_shapefile_zip_bytes), "application/zip")},
    )
    file_id = upload_res.json()["id"]

    meas_res = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_res.status_code == 200
    measurements = meas_res.json()["measurements"]
    assert len(measurements) == 3

    # Check all parcel polygon areas
    for poly_m in measurements:
        assert poly_m["geometry_type"] == "Polygon"
        assert poly_m["area"] > 0
        assert poly_m["unit"] == "m²"


def test_measurements_not_found(client: TestClient):
    """Test fetching measurements for nonexistent file ID returns HTTP 404."""
    response = client.get("/api/files/nonexistent_id_abc/measurements/")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_unsupported_geometry_type_does_not_crash():
    """Test that unsupported geometry types (e.g. GeometryCollection) return clear responses without crashing."""
    p1 = Point(77.59, 12.97)
    l1 = LineString([(77.59, 12.97), (77.60, 12.98)])
    geom_col = GeometryCollection([p1, l1])

    result = measurement_service.measure_single_geometry(
        feature_id=99,
        geometry=geom_col,
        source_crs=pyproj.CRS.from_epsg(4326),
    )

    assert result["feature_id"] == 99
    assert result["geometry_type"] == "GeometryCollection"
    assert result["measurement"] is None
    assert "not supported" in result["message"]


def test_empty_geometry_handling():
    """Test that empty or null geometry returns gracefully without error."""
    empty_poly = Polygon()
    result = measurement_service.measure_single_geometry(
        feature_id=100,
        geometry=empty_poly,
        source_crs=pyproj.CRS.from_epsg(4326),
    )

    assert result["feature_id"] == 100
    assert result["measurement"] is None
    assert "empty" in result["message"].lower()
