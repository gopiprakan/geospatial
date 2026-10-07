"""Tests for CRS analysis, local UTM determination, and metric reprojection."""

import pyproj
from shapely.geometry import LineString, Point, Polygon

from app.services.crs import crs_service
from app.services.measurement import measurement_service


def test_utm_zone_determination_global_cities():
    """Verify UTM zone and EPSG code calculation across both Northern and Southern hemispheres."""
    # 1. Bangalore, India (Lat 12.97° N, Lon 77.59° E) -> Zone 43N (EPSG:32643)
    crs_blr = crs_service.determine_utm_crs(lon=77.59, lat=12.97)
    assert crs_blr.to_epsg() == 32643

    # 2. London, UK (Lat 51.51° N, Lon -0.13° W) -> Zone 30N (EPSG:32630)
    crs_lon = crs_service.determine_utm_crs(lon=-0.13, lat=51.51)
    assert crs_lon.to_epsg() == 32630

    # 3. Sydney, Australia (Lat -33.87° S, Lon 151.21° E) -> Zone 56S (EPSG:32756)
    crs_syd = crs_service.determine_utm_crs(lon=151.21, lat=-33.87)
    assert crs_syd.to_epsg() == 32756

    # 4. New York, USA (Lat 40.71° N, Lon -74.01° W) -> Zone 18N (EPSG:32618)
    crs_nyc = crs_service.determine_utm_crs(lon=-74.01, lat=40.71)
    assert crs_nyc.to_epsg() == 32618


def test_area_is_not_calculated_in_degrees():
    """
    CRITICAL: Verify that area is never calculated in square degrees.
    In EPSG:4326, a 0.01 x 0.01 degree square has raw .area = 0.0001 (square degrees).
    The service must reproject to UTM and yield approx 1.2 x 10^6 m².
    """
    # 0.01 degree box near equator/Bangalore
    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)])
    raw_degree_area = poly.area
    assert raw_degree_area < 0.001  # Degree calculation produces meaningless fraction

    result = measurement_service.measure_single_geometry(
        feature_id=0,
        geometry=poly,
        source_crs=pyproj.CRS.from_epsg(4326),
    )

    assert result["unit"] == "m²"
    # Should be approximately 1.2 square km (1,200,000 m²)
    assert result["area"] > 1_000_000.0
    assert result["area"] < 1_500_000.0


def test_length_is_not_calculated_in_degrees():
    """
    CRITICAL: Verify that length is never calculated in degrees.
    In EPSG:4326, a 0.01 degree line has raw .length = 0.01 (degrees).
    The service must reproject to UTM and yield approx 1,100 meters.
    """
    line = LineString([(77.59, 12.97), (77.60, 12.97)])
    raw_degree_length = line.length
    assert raw_degree_length < 0.1  # Degree calculation produces fraction

    result = measurement_service.measure_single_geometry(
        feature_id=1,
        geometry=line,
        source_crs=pyproj.CRS.from_epsg(4326),
    )

    assert result["unit"] == "m"
    # Approx 1.08 km (1080 m)
    assert 1000.0 <= result["length"] <= 1200.0


def test_missing_crs_fallback_with_geographic_bounds():
    """Verify that geometries without CRS but with geographic coordinate bounds are handled gracefully."""
    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)])
    proj_crs = crs_service.get_projected_crs(
        source_crs=None,
        bounds=poly.bounds,
        centroid=(77.595, 12.975),
    )
    assert proj_crs.to_epsg() == 32643


def test_existing_projected_metric_crs_preserved():
    """Verify that datasets already in a metric projected CRS (e.g. UTM) are preserved."""
    utm_crs = pyproj.CRS.from_epsg(32643)
    resolved = crs_service.get_projected_crs(
        source_crs=utm_crs,
        centroid=(780000.0, 1435000.0),
    )
    assert resolved.to_epsg() == 32643


def test_transform_geometry_coordinates():
    """Verify geometry reprojection accurately converts coordinates from degrees to meters."""
    pt_wgs84 = Point(77.5946, 12.9716)
    pt_projected = crs_service.transform_geometry(
        pt_wgs84,
        source_crs=pyproj.CRS.from_epsg(4326),
        target_crs=pyproj.CRS.from_epsg(32643),
    )
    # UTM coordinates are large meter numbers (e.g. Easting ~781,000 m, Northing ~1,435,000 m)
    assert pt_projected.x > 100_000.0
    assert pt_projected.y > 100_000.0
