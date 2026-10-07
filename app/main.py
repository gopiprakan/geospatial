"""Main FastAPI application module."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import GeospatialError
from app.routes.files import router as files_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geospatial-api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for initialization and cleanup."""
    logger.info("Initializing Geospatial File Measurement API...")
    settings.ensure_directories()
    yield
    logger.info("Shutting down Geospatial File Measurement API...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Production-quality REST API for uploading, validating, and measuring geospatial files "
        "(.kml and Shapefile .zip archives). Features automatic CRS detection, intelligent "
        "local UTM reprojection, and precise metric area/length calculations."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(files_router)


# Global Exception Handlers
@app.exception_handler(GeospatialError)
async def geospatial_error_handler(request: Request, exc: GeospatialError) -> JSONResponse:
    """Handle custom geospatial domain errors with appropriate status codes."""
    logger.warning(f"GeospatialError on {request.url.path}: {exc.message} (HTTP {exc.status_code})")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors cleanly."""
    errors = exc.errors()
    first_error = errors[0]["msg"] if errors else "Invalid request data."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": f"Request validation failed: {first_error}"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled server exceptions safely without crashing the service."""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )


@app.get(
    "/health",
    tags=["System"],
    summary="Health check endpoint",
)
def health_check():
    """Verify service health and readiness."""
    return {"status": "healthy", "version": settings.app_version}


@app.get(
    "/",
    tags=["System"],
    summary="API Root Information",
)
def root():
    """Root endpoint welcoming clients and linking to docs."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "endpoints": {
            "upload": "POST /api/files/",
            "file_info": "GET /api/files/{id}/",
            "measurements": "GET /api/files/{id}/measurements/",
        },
    }
