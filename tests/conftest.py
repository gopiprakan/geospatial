"""Pytest configuration and reusable test fixtures for Geospatial API testing."""

import io
import os
import tempfile
import zipfile
import pytest
from fastapi.testclient import TestClient
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

from app.main import app
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure database is clean before each test."""
    storage_service.clear()
    yield
    storage_service.clear()


@pytest.fixture
def client():
    """FastAPI test client instance."""
    return TestClient(app)


@pytest.fixture
def sample_kml_bytes() -> bytes:
    """Generate a valid KML file containing Point, LineString, and Polygon features."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Survey Dataset</name>
    <Placemark>
      <name>Survey Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.6000,12.9700,0
              77.6000,12.9800,0
              77.5900,12.9800,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Survey Line</name>
      <LineString>
        <coordinates>
          77.5900,12.9700,0
          77.6000,12.9800,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Survey Point</name>
      <Point>
        <coordinates>77.5946,12.9716,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    return kml_content.encode("utf-8")


@pytest.fixture
def corrupted_kml_bytes() -> bytes:
    """Generate a malformed XML KML byte stream."""
    return b"<kml><Document><Placemark><name>Broken</name><Point><unclosed>"


@pytest.fixture
def valid_shapefile_zip_bytes() -> bytes:
    """Generate a valid ZIP archive containing a Shapefile (.shp, .shx, .dbf, .prj)."""
    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)])
    line = LineString([(77.59, 12.97), (77.60, 12.98)])
    pt = Point(77.5946, 12.9716)

    gdf = gpd.GeoDataFrame(
        [
            {"id": 1, "name": "Poly 1", "geometry": poly},
            {"id": 2, "name": "Line 1", "geometry": line},
            {"id": 3, "name": "Point 1", "geometry": pt},
        ],
        crs="EPSG:4326",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, "parcels.shp")
        gdf.to_file(shp_path)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
                filepath = os.path.join(tmpdir, f"parcels{ext}")
                if os.path.exists(filepath):
                    z.write(filepath, arcname=f"parcels{ext}")

        zip_buffer.seek(0)
        return zip_buffer.getvalue()


@pytest.fixture
def incomplete_shapefile_zip_bytes() -> bytes:
    """Generate a Shapefile ZIP missing the required .shx companion."""
    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.97)])
    gdf = gpd.GeoDataFrame([{"id": 1, "geometry": poly}], crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, "incomplete.shp")
        gdf.to_file(shp_path)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            # Intentionally omit .shx
            for ext in [".shp", ".dbf", ".prj"]:
                filepath = os.path.join(tmpdir, f"incomplete{ext}")
                if os.path.exists(filepath):
                    z.write(filepath, arcname=f"incomplete{ext}")

        zip_buffer.seek(0)
        return zip_buffer.getvalue()


@pytest.fixture
def zip_without_shapefile_bytes() -> bytes:
    """Generate a valid ZIP that contains no .shp file."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("readme.txt", "This is just a text file, not a shapefile.")
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


@pytest.fixture
def zip_slip_attack_bytes() -> bytes:
    """Generate a ZIP archive attempting Zip Slip directory traversal."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("../malicious_target.txt", "Malicious content escaping directory.")
    zip_buffer.seek(0)
    return zip_buffer.getvalue()
