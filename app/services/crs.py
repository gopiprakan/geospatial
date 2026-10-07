"""CRS (Coordinate Reference System) detection, validation, and reprojection service."""

import logging
from typing import Optional, Tuple
import numpy as np
import pyproj
import shapely
from shapely.geometry.base import BaseGeometry

from app.exceptions import CRSError

logger = logging.getLogger(__name__)


class CRSService:
    """Service handling CRS identification, validation, and projected metric transformations."""

    @staticmethod
    def parse_crs(crs_input: Optional[object]) -> Optional[pyproj.CRS]:
        """
        Safely parse various CRS inputs into a pyproj.CRS object.

        Returns None if CRS is missing or unparseable.
        """
        if crs_input is None:
            return None
        try:
            return pyproj.CRS.from_user_input(crs_input)
        except Exception as e:
            logger.warning(f"Could not parse CRS input '{crs_input}': {e}")
            return None

    @staticmethod
    def get_crs_name(crs: Optional[pyproj.CRS]) -> str:
        """Return a standardized string representation of the CRS (e.g. 'EPSG:4326')."""
        if crs is None:
            return "UNKNOWN"
        epsg = crs.to_epsg()
        if epsg:
            return f"EPSG:{epsg}"
        auth = crs.to_authority()
        if auth:
            return f"{auth[0]}:{auth[1]}"
        return crs.name or "UNKNOWN"

    @staticmethod
    def determine_utm_crs(lon: float, lat: float) -> pyproj.CRS:
        """
        Determine the appropriate local UTM (Universal Transverse Mercator) projected CRS
        for a given longitude and latitude centroid.

        UTM zones span 6° of longitude:
          Zone = floor((lon + 180) / 6) + 1  (1 to 60)
          Northern Hemisphere: EPSG: 32600 + zone
          Southern Hemisphere: EPSG: 32700 + zone
        """
        # Normalize longitude to [-180, 180)
        norm_lon = (lon + 180.0) % 360.0 - 180.0
        zone = int((norm_lon + 180.0) / 6.0) + 1
        zone = max(1, min(60, zone))

        epsg_code = (32600 + zone) if lat >= 0 else (32700 + zone)
        return pyproj.CRS.from_epsg(epsg_code)

    @classmethod
    def get_projected_crs(
        cls,
        source_crs: Optional[pyproj.CRS],
        bounds: Optional[Tuple[float, float, float, float]] = None,
        centroid: Optional[Tuple[float, float]] = None,
    ) -> pyproj.CRS:
        """
        Determine the most appropriate projected metric CRS for geometry measurement.

        If source CRS is geographic (degrees), computes the local UTM zone based on location.
        If source CRS is EPSG:3857 (Web Mercator), reprojects to local UTM to eliminate extreme area distortion.
        If source CRS is already an accurate local projected metric CRS, preserves it.
        """
        # If source CRS is missing, check if coordinates fall in geographic bounds [-180, 180, -90, 90]
        if source_crs is None:
            if bounds and cls._bounds_within_geographic(bounds):
                logger.info("Missing CRS with bounds in [-180, 180, -90, 90]. Defaulting to EPSG:4326.")
                source_crs = pyproj.CRS.from_epsg(4326)
            else:
                raise CRSError("CRS is missing and dataset coordinates are not in geographic range.")

        # If source is EPSG:3857 (Web Mercator), convert centroid to lat/lon and use UTM
        epsg = source_crs.to_epsg()
        if epsg == 3857 and centroid:
            try:
                to_wgs84 = pyproj.Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
                lon, lat = to_wgs84.transform(centroid[0], centroid[1])
                return cls.determine_utm_crs(lon, lat)
            except Exception:
                pass

        # If already projected and not Web Mercator, check linear units
        if source_crs.is_projected and epsg != 3857:
            axis_units = [a.unit_name for a in source_crs.axis_info]
            if any(u in ["metre", "meter", "m"] for u in axis_units):
                return source_crs

        # If geographic, calculate UTM from centroid or bounds
        if centroid:
            lon, lat = centroid
        elif bounds:
            minx, miny, maxx, maxy = bounds
            lon = (minx + maxx) / 2.0
            lat = (miny + maxy) / 2.0
        else:
            lon, lat = 0.0, 0.0

        return cls.determine_utm_crs(lon, lat)

    @staticmethod
    def _bounds_within_geographic(bounds: Tuple[float, float, float, float]) -> bool:
        """Check whether bounding box values lie within valid longitude/latitude ranges."""
        minx, miny, maxx, maxy = bounds
        return -180.0 <= minx <= 180.0 and -180.0 <= maxx <= 180.0 and -90.0 <= miny <= 90.0 and -90.0 <= maxy <= 90.0

    @classmethod
    def transform_geometry(
        cls,
        geometry: BaseGeometry,
        source_crs: pyproj.CRS,
        target_crs: pyproj.CRS,
    ) -> BaseGeometry:
        """
        Reproject a Shapely geometry from source_crs to target_crs safely,
        handling 2D and 3D coordinate sequences.
        """
        if source_crs == target_crs:
            return geometry

        transformer = pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)

        def _transform_coords(coords: np.ndarray) -> np.ndarray:
            if coords.shape[1] == 3:
                nx, ny = transformer.transform(coords[:, 0], coords[:, 1])
                return np.column_stack([nx, ny, coords[:, 2]])
            nx, ny = transformer.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([nx, ny])

        try:
            return shapely.transform(geometry, _transform_coords)
        except Exception as e:
            raise CRSError(f"Geometry coordinate reprojection failed: {e}")


crs_service = CRSService()
