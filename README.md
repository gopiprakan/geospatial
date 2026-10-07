# Geospatial File Measurement API

A production-quality REST API built with **Python 3.11+** and **FastAPI** that ingests geospatial datasets (`.kml` and Shapefile `.zip` archives), validates geometry integrity, resolves Coordinate Reference Systems (CRS) dynamically into local projected metric coordinates (UTM), and calculates accurate feature measurements (polygon areas in $\text{m}^2$, linestring lengths in $\text{m}$, and point locations).

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Architecture & Processing Flow](#architecture--processing-flow)
- [CRS Strategy & Coordinate Geodesy](#crs-strategy--coordinate-geodesy)
- [API Documentation & Endpoints](#api-documentation--endpoints)
  - [1. Upload File (`POST /api/files/`)](#1-upload-file-post-apifiles)
  - [2. Get File Information (`GET /api/files/{id}/`)](#2-get-file-information-get-apifilesid)
  - [3. Get Feature Measurements (`GET /api/files/{id}/measurements/`)](#3-get-feature-measurements-get-apifilesidmeasurements)
- [Error Handling & Edge Cases](#error-handling--edge-cases)
- [Installation & Setup](#installation--setup)
- [Running the Application](#running-the-application)
- [Running Tests](#running-tests)
- [What Was Learned](#what-was-learned)
- [Future Scope & Production Roadmap](#future-scope--production-roadmap)

---

## Project Overview

In Geographic Information Systems (GIS), computing physical distances and surface areas directly from raw latitude/longitude coordinates (such as WGS84 `EPSG:4326`) produces inaccurate and distorted results because degrees are angular units, not uniform planar distances.

The **Geospatial File Measurement API** addresses this challenge by providing a robust, automated backend service that:
1. Ingests geospatial files in **Keyhole Markup Language (`.kml`)** or **ESRI Shapefiles (packaged as `.zip`)**.
2. Performs strict archive inspection and defense against directory traversal attacks (**Zip Slip**).
3. Verifies mandatory Shapefile companions (`.shp`, `.shx`, `.dbf`).
4. Determines the dataset's geographic centroid and dynamically computes the optimal **Universal Transverse Mercator (UTM)** projected CRS zone.
5. Reprojects features into conformal metric units (meters) to compute precise areas ($\text{m}^2$) and lengths ($\text{m}$).
6. Persists file metadata and pre-computed measurements with an atomic, thread-safe SQLite datastore.

---

## Key Features

- **Multi-Format Ingestion**: Full support for `.kml` files (including multi-layer placemarks and 3D coordinates) and `.zip` Shapefile archives.
- **Dynamic Projected CRS Selection**: Automates local UTM zone detection based on dataset centroid longitude and latitude, preventing degree-distortion errors.
- **Accurate Metric Calculations**:
  - `Polygon` and `MultiPolygon`: Area in square meters ($\text{m}^2$).
  - `LineString` and `MultiLineString`: Length in meters ($\text{m}$).
  - `Point` and `MultiPoint`: Preserved with `measurement: null`.
- **Fault-Tolerant Geometry Engine**: Handles unsupported geometry types (e.g. `GeometryCollection`), empty geometries, and malformed features without crashing the server.
- **Enterprise-Grade Security**:
  - Path traversal (Zip Slip) validation on all zip archive extractions.
  - Multipart chunk size validation against configurable upload thresholds.
- **Interactive OpenAPI Documentation**: Automatic Swagger UI at `/docs` and ReDoc at `/redoc`.
- **Extensive Test Coverage**: 23 automated unit and integration tests using `pytest` and `TestClient`.

---

## Tech Stack

| Technology | Purpose |
| :--- | :--- |
| **Python 3.11+** | Modern Python runtime utilizing type annotations and performance improvements. |
| **FastAPI** | High-performance asynchronous web framework for RESTful APIs. |
| **Uvicorn** | Lightning-fast ASGI production web server. |
| **GeoPandas** | Spatial operations and tabular geospatial data structures. |
| **Shapely** | Planar geometry manipulation, validation, and measurement. |
| **PyProj** | Cartographic projections and Coordinate Reference System (CRS) transformations. |
| **Fiona / Pyogrio** | High-performance GDAL vector file I/O drivers. |
| **Pydantic v2** | Strict data validation, schema enforcement, and JSON serialization. |
| **SQLite3** | Thread-safe, atomic transactional storage for metadata and feature records. |
| **pytest** | Robust test runner with fixtures and comprehensive test cases. |

---

## Architecture & Processing Flow

The project follows clean architecture principles with clear separation of concerns across routes, domain services, storage repositories, and utilities:

```
Upload
  ↓
Validation (Extension, Size, Zip Slip Security)
  ↓
File Processing (KML / Shapefile Extraction)
  ↓
Feature Extraction (GeoDataFrame Normalization)
  ↓
CRS Handling (Centroid Analysis & Local UTM Selection)
  ↓
Measurement Calculation (Metric Area / Length Transformations)
  ↓
Storage Persistence (SQLite Atomic Commit)
  ↓
API Response (Pydantic Models)
```

### Directory Structure

```text
geospatial/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application instance, lifespan, middleware & error handlers
│   ├── config.py                # Environment configuration (Pydantic Settings)
│   ├── exceptions.py            # Domain-specific exception hierarchy
│   ├── routes/
│   │   ├── __init__.py
│   │   └── files.py             # REST API endpoints (Upload, Info, Measurements)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── file.py              # Pydantic models & serializers
│   │   └── error.py             # Standardized error schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── crs.py               # CRS analysis, UTM zone calculation & coordinate reprojection
│   │   ├── file_processor.py    # KML & Shapefile validation, extraction & reading
│   │   ├── measurement.py       # Metric area & length computation engine
│   │   └── storage.py           # SQLite repository for file records and measurements
│   └── utils/
│       ├── __init__.py
│       └── file_utils.py        # Safe zip extraction, path traversal defense, component checks
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures (sample KML, Shapefiles, bad files)
│   ├── test_upload.py           # Upload validation, format checks & error testing
│   ├── test_measurements.py     # Geometry calculations, units & unsupported geometry handling
│   └── test_crs.py              # UTM determination, degree vs meter verification
├── uploads/
│   └── .gitkeep                 # Managed upload staging directory
├── data/
│   └── .gitkeep                 # SQLite database storage directory
├── .env.example                 # Environment configuration template
├── .gitignore                   # Git exclusion rules
├── requirements.txt             # Locked project dependencies
├── README.md                    # Project documentation
└── run.py                       # CLI execution entrypoint
```

---

## CRS Strategy & Coordinate Geodesy

### Why Geographic CRS (EPSG:4326) Cannot Be Used Directly

In a geographic Coordinate Reference System like **WGS84 (`EPSG:4326`)**, positions are represented as angular coordinates: **latitude** ($\phi$) and **longitude** ($\lambda$) in degrees.

1. **Angular Units vs. Linear Units**: A degree is an angle, not a constant distance.
2. **Latitudinal Convergence**: While 1 degree of latitude is approximately 111 km everywhere, 1 degree of longitude is ~111.32 km at the equator, but shrinks with the cosine of latitude:
   $$\text{Distance per degree longitude} \approx 111.32 \times \cos(\text{latitude}) \text{ km}$$
   At 60° latitude, 1 degree of longitude is only ~55.66 km, and at the poles, it converges to 0.
3. **Severe Distortion**: If one executes Euclidean planar formulas directly on degree coordinates (e.g., `polygon.area` or `line.length`), the result is expressed in meaningless "square degrees" or "degrees". For example, a parcel of 1.2 square kilometers would return a raw value of `0.0001`!

### The Dynamic Projection Strategy

To guarantee true physical measurements, this API implements the following reprojection workflow:

```
[Uploaded File Features]
           │
           ▼
[Check Source CRS]
  ├── If Missing: Inspect coordinate bounds. If in [-180, 180] x [-90, 90], infer EPSG:4326.
  ├── If Projected (Metric, e.g. UTM): Retain original CRS.
  └── If Geographic (EPSG:4326) or Web Mercator (EPSG:3857):
           │
           ▼
[Determine Geographic Centroid]
  (lon, lat) computed from dataset or feature geometry
           │
           ▼
[Compute Local UTM Zone]
  Zone = floor((lon + 180) / 6) + 1  (clamped 1 to 60)
  EPSG = (32600 + Zone) if lat >= 0 else (32700 + Zone)
           │
           ▼
[Reproject Geometry via PyProj & Shapely]
  Coordinates converted from angular (deg) to conformal planar meters (m)
           │
           ▼
[Calculate Accurate Metric Measurements]
  area = round(geom.area, 2)  --> m²
  length = round(geom.length, 2) --> m
```

---

## API Documentation & Endpoints

### 1. Upload File (`POST /api/files/`)

Accepts a multipart file upload (`.kml` or `.zip` containing a Shapefile).

**Request**:
```http
POST /api/files/ HTTP/1.1
Content-Type: multipart/form-data; boundary=boundary

--boundary
Content-Disposition: form-data; name="file"; filename="survey.kml"
Content-Type: application/vnd.google-earth.kml+xml

[Binary or Text KML / ZIP Payload]
--boundary--
```

**Response (`201 Created`)**:
```json
{
  "id": "abc123",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

---

### 2. Get File Information (`GET /api/files/{id}/`)

Retrieves metadata and processing status for an uploaded file.

**Request**:
```http
GET /api/files/abc123/ HTTP/1.1
```

**Response (`200 OK`)**:
```json
{
  "id": "abc123",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

---

### 3. Get Feature Measurements (`GET /api/files/{id}/measurements/`)

Returns measurement calculations for every feature in the dataset in metric units.

**Request**:
```http
GET /api/files/abc123/measurements/ HTTP/1.1
```

**Response (`200 OK`)**:
```json
{
  "file_id": "abc123",
  "measurements": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "area": 12500.50,
      "unit": "m²"
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "length": 850.25,
      "unit": "m"
    },
    {
      "feature_id": 2,
      "geometry_type": "Point",
      "measurement": null
    }
  ]
}
```

---

## Error Handling & Edge Cases

The server handles bad requests, security exploits, and invalid geospatial data cleanly with standardized JSON error responses:

| Condition | HTTP Status | Detail Message Example |
| :--- | :--- | :--- |
| **Unsupported extension** | `400 Bad Request` | `{"detail": "Unsupported file extension '.pdf'. Allowed extensions are: .kml, .zip"}` |
| **Empty file (0 bytes)** | `400 Bad Request` | `{"detail": "Uploaded file is empty (0 bytes)."}` |
| **File too large** | `413 Payload Too Large` | `{"detail": "Uploaded file exceeds maximum allowed size of 50 MB."}` |
| **Corrupted KML** | `422 Unprocessable Entity` | `{"detail": "Corrupted or invalid KML file: malformed XML (...)"}` |
| **Invalid ZIP** | `422 Unprocessable Entity` | `{"detail": "Uploaded file is not a valid ZIP archive: Bad CRC"}` |
| **Missing `.shp` file** | `422 Unprocessable Entity` | `{"detail": "No .shp file found in uploaded ZIP archive."}` |
| **Missing `.shx` or `.dbf`** | `422 Unprocessable Entity` | `{"detail": "Shapefile archive is missing mandatory component(s): .shx"}` |
| **Zip Slip attack** | `422 Unprocessable Entity` | `{"detail": "Attempted path traversal (Zip Slip) detected for member: ../hack.shp"}` |
| **File ID not found** | `404 Not Found` | `{"detail": "File with ID 'nonexistent_id' not found."}` |
| **Unsupported Geometry** | `200 OK` (Per-feature) | `{"feature_id": 3, "geometry_type": "GeometryCollection", "measurement": null, "message": "Measurement not supported for geometry type 'GeometryCollection'."}` |

---

## Installation & Setup

### 1. Prerequisites
- **Python 3.11+** installed.
- Git installed.

### 2. Clone Repository
```bash
git clone https://github.com/your-username/geospatial-file-measurement-api.git
cd geospatial-file-measurement-api
```

### 3. Create & Activate Virtual Environment

**On Windows (Command Prompt / PowerShell)**:
```bash
python -m venv venv
.\venv\Scripts\activate
```

**On Linux / macOS**:
```bash
python -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

---

## Running the Application

### Development Mode (with hot-reload)
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or using the convenience runner script:
```bash
python run.py
```

### Accessing the Interactive API Documentation
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Running Tests

The test suite contains 23 comprehensive tests covering uploads, invalid files, security protections, geometry measurement accuracy, and CRS geodesic transformations.

Run tests with `pytest`:
```bash
pytest -v
```

Run test suite with detailed output and coverage:
```bash
pytest -v -s --tb=short
```

---

## What Was Learned

1. **FastAPI & REST Architecture**: Designing clean, type-safe API contracts with Pydantic v2, custom serializers, lifespan management, and modular APIRouters.
2. **Geospatial Coordinate Geodesy**: Understanding the critical differences between geographic angular ellipsoidal coordinates (EPSG:4326) and conformal projected planar coordinates (UTM).
3. **GeoPandas & Pyogrio Vector I/O**: Efficiently parsing diverse vector formats (KML layers, Shapefile bundles) and normalizing them into unified GeoDataFrames.
4. **PyProj & Coordinate Transformers**: Dynamically computing UTM zones from dataset bounding box centroids and performing 2D and 3D coordinate array transformations.
5. **Defensive Archive Processing**: Implementing Zip Slip prevention to defend against directory traversal attacks during compressed Shapefile extraction.
6. **Graceful Degradation & Resilience**: Designing non-crashing fallbacks for multi-geometry types, empty features, and corrupted XML trees.

---

## Future Scope & Production Roadmap

- **PostgreSQL / PostGIS Integration**: Migrate from SQLite to PostGIS to support spatial indexing (R-Tree / GiST), large-scale spatial queries, and multi-tenant clustering.
- **Asynchronous Background Processing**: Offload massive geospatial datasets (gigabyte-sized files) to Celery or ARQ with Redis task queues and WebSocket status updates.
- **Extended Spatial Formats**: Add native parsers for **GeoJSON**, **GeoPackage (`.gpkg`)**, **FlatGeobuf**, and **GeoTIFF** raster statistics.
- **Authentication & RBAC**: Implement OAuth2 / JWT authentication, rate limiting, and API keys for user access tiers.
- **Direct Cloud Ingestion**: Stream uploads directly to AWS S3, Google Cloud Storage, or Azure Blob Storage via signed URLs.
- **Interactive Map Visualization**: Embed Kepler.gl or Leaflet/MapLibre web viewers to inspect feature boundaries visually in the browser.
- **Automated CI/CD**: GitHub Actions workflows for continuous linting (Ruff/Black), type checking (Mypy), and multi-OS matrix testing.
