"""Geospatial measurement service for calculating metric areas and lengths."""

import logging
from typing import Any, Dict, List, Optional
import geopandas as gpd
import pyproj
from shapely.geometry.base import BaseGeometry

from app.services.crs import crs_service

logger = logging.getLogger(__name__)

SUPPORTED_AREA_TYPES = {"Polygon", "MultiPolygon"}
SUPPORTED_LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


class MeasurementService:
    """Calculates metric measurements (m, m²) for geospatial geometries."""

    @classmethod
    def measure_single_geometry(
        cls,
        feature_id: int,
        geometry: Optional[BaseGeometry],
        source_crs: Optional[pyproj.CRS],
        properties: Optional[Dict[str, Any]] = None,
        target_projected_crs: Optional[pyproj.CRS] = None,
    ) -> Dict[str, Any]:
        """
        Calculate measurement for a single geometry feature.

        Returns a dictionary compliant with FeatureMeasurement schema.
        Never crashes on invalid, corrupted, or unsupported geometries.
        """
        base_result: Dict[str, Any] = {
            "feature_id": feature_id,
            "geometry_type": "Unknown",
        }
        if properties:
            base_result["properties"] = properties

        if geometry is None or geometry.is_empty:
            base_result["geometry_type"] = "Empty" if geometry and geometry.is_empty else "None"
            base_result["measurement"] = None
            base_result["message"] = "Geometry is empty or null."
            return base_result

        geom_type = geometry.geom_type
        base_result["geometry_type"] = geom_type

        # Point types require no measurement per specification
        if geom_type in POINT_TYPES:
            base_result["measurement"] = None
            return base_result

        # Check for unsupported geometry types
        if geom_type not in SUPPORTED_AREA_TYPES and geom_type not in SUPPORTED_LENGTH_TYPES:
            base_result["measurement"] = None
            base_result["message"] = f"Measurement not supported for geometry type '{geom_type}'."
            return base_result

        # Determine target projected metric CRS
        try:
            if target_projected_crs is None:
                centroid_point = geometry.centroid
                centroid_coords = (centroid_point.x, centroid_point.y) if not centroid_point.is_empty else None
                bounds = geometry.bounds
                target_crs = crs_service.get_projected_crs(
                    source_crs=source_crs,
                    bounds=bounds,
                    centroid=centroid_coords,
                )
            else:
                target_crs = target_projected_crs

            # Transform geometry to projected metric CRS
            effective_source = source_crs or pyproj.CRS.from_epsg(4326)
            proj_geom = crs_service.transform_geometry(geometry, effective_source, target_crs)

            if geom_type in SUPPORTED_AREA_TYPES:
                area_m2 = round(float(proj_geom.area), 2)
                base_result["area"] = area_m2
                base_result["unit"] = "m²"
            elif geom_type in SUPPORTED_LENGTH_TYPES:
                length_m = round(float(proj_geom.length), 2)
                base_result["length"] = length_m
                base_result["unit"] = "m"

        except Exception as e:
            logger.warning(f"Feature {feature_id} measurement failed: {e}")
            base_result["measurement"] = None
            base_result["message"] = f"Measurement calculation failed: {str(e)}"

        return base_result

    @classmethod
    def measure_geodataframe(
        cls,
        gdf: gpd.GeoDataFrame,
        source_crs: Optional[pyproj.CRS] = None,
    ) -> List[Dict[str, Any]]:
        """
        Process and calculate measurements for all features in a GeoDataFrame.
        Determines dataset-level optimal projected CRS and transforms features.
        """
        if gdf.empty:
            return []

        # Resolve dataset CRS
        effective_source = source_crs or crs_service.parse_crs(gdf.crs)

        # Estimate target projected CRS for the entire dataset
        target_crs: Optional[pyproj.CRS] = None
        try:
            total_bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
            centroid_x = (total_bounds[0] + total_bounds[2]) / 2.0
            centroid_y = (total_bounds[1] + total_bounds[3]) / 2.0
            target_crs = crs_service.get_projected_crs(
                source_crs=effective_source,
                bounds=tuple(total_bounds),
                centroid=(centroid_x, centroid_y),
            )
        except Exception as e:
            logger.warning(f"Could not determine dataset-level projected CRS: {e}")

        measurements: List[Dict[str, Any]] = []

        # Iterate over features
        for idx, row in gdf.iterrows():
            geom = row.geometry if hasattr(row, "geometry") else None
            # Extract non-geometry properties
            props = {
                k: v
                for k, v in row.items()
                if k != "geometry" and v is not None and not (isinstance(v, float) and v != v)
            }

            meas = cls.measure_single_geometry(
                feature_id=int(idx),
                geometry=geom,
                source_crs=effective_source,
                properties=props if props else None,
                target_projected_crs=target_crs,
            )
            measurements.append(meas)

        return measurements


measurement_service = MeasurementService()
