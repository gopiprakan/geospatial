"""Geospatial file processor service for handling KML and Shapefile ZIP archives."""

import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

import fiona
import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Point, LineString, Polygon

from app.exceptions import (
    CorruptedFileError,
    EmptyUploadError,
    InvalidFileFormatError,
)
from app.services.crs import crs_service
from app.utils.file_utils import (
    cleanup_path,
    safe_extract_zip,
    validate_file_extension,
    verify_shapefile_components,
)

logger = logging.getLogger(__name__)

# Enable KML driver support in Fiona
try:
    if "KML" not in fiona.supported_drivers:
        fiona.drvsupport.supported_drivers["KML"] = "rw"
    if "LIBKML" not in fiona.supported_drivers:
        fiona.drvsupport.supported_drivers["LIBKML"] = "rw"
except Exception as e:
    logger.debug(f"Fiona KML driver registration: {e}")


class FileProcessorService:
    """Service to safely parse, validate, and load geospatial files into GeoPandas DataFrames."""

    @classmethod
    def process_file(cls, file_path: Path, filename: str) -> Tuple[gpd.GeoDataFrame, str]:
        """
        Main entry point for processing an uploaded geospatial file (.kml or .zip).

        Args:
            file_path: Local path to the uploaded file.
            filename: Original user filename.

        Returns:
            Tuple of (GeoDataFrame containing features, CRS string e.g. 'EPSG:4326').
        """
        ext = validate_file_extension(filename)

        if not file_path.exists() or file_path.stat().st_size == 0:
            raise EmptyUploadError("Uploaded file is empty.")

        if ext == ".kml":
            return cls.process_kml(file_path)
        elif ext == ".zip":
            return cls.process_shapefile_zip(file_path)
        else:
            raise InvalidFileFormatError(f"Unsupported extension '{ext}'. Only .kml and .zip are supported.")

    @classmethod
    def process_kml(cls, kml_path: Path) -> Tuple[gpd.GeoDataFrame, str]:
        """
        Read and validate a KML file into a GeoDataFrame with CRS.
        """
        # Validate XML well-formedness first
        try:
            tree = ET.parse(kml_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise CorruptedFileError(f"Corrupted or invalid KML file: malformed XML ({e})")
        except Exception as e:
            raise CorruptedFileError(f"Unable to parse KML file: {e}")

        # Attempt reading via Fiona / pyogrio / GeoPandas
        gdf: Optional[gpd.GeoDataFrame] = None

        # 1. Try reading with Pyogrio / Fiona layer inspection
        try:
            layers = pyogrio.list_layers(kml_path)
            if len(layers) > 0:
                layer_gdfs: List[gpd.GeoDataFrame] = []
                for layer_name in layers[:, 0]:
                    try:
                        layer_df = gpd.read_file(kml_path, layer=layer_name)
                        if not layer_df.empty:
                            layer_gdfs.append(layer_df)
                    except Exception as layer_err:
                        logger.debug(f"Could not read layer {layer_name}: {layer_err}")

                if layer_gdfs:
                    gdf = pd.concat(layer_gdfs, ignore_index=True)
                    if not isinstance(gdf, gpd.GeoDataFrame):
                        gdf = gpd.GeoDataFrame(gdf)
        except Exception as e:
            logger.debug(f"pyogrio list_layers failed: {e}")

        # 2. Try standard gpd.read_file
        if gdf is None or gdf.empty:
            try:
                gdf = gpd.read_file(kml_path)
            except Exception as e:
                logger.debug(f"gpd.read_file failed on KML: {e}")

        # 3. Robust XML fallback for Placemark extraction if GDAL drivers found no geometries
        if gdf is None or gdf.empty:
            gdf = cls._parse_kml_xml_fallback(root)

        if gdf is None or gdf.empty:
            # File is a valid KML structure but contains 0 placemark features
            gdf = gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")

        # KML standard (OGC KML 2.2) is defined in WGS84 (EPSG:4326)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)

        crs_str = crs_service.get_crs_name(gdf.crs)
        return gdf, crs_str

    @classmethod
    def _parse_kml_xml_fallback(cls, root: ET.Element) -> gpd.GeoDataFrame:
        """
        Direct XML parsing fallback to extract Point, LineString, and Polygon placemarks.
        """
        features: List[dict] = []
        placemarks = root.findall(".//{http://www.opengis.net/kml/2.2}Placemark") or root.findall(".//Placemark")

        for p in placemarks:
            name_elem = p.find("{http://www.opengis.net/kml/2.2}name") or p.find("name")
            name = name_elem.text if name_elem is not None else ""

            # 1. Point
            pt_coord = p.find(".//{http://www.opengis.net/kml/2.2}Point/{http://www.opengis.net/kml/2.2}coordinates") or p.find(".//Point/coordinates")
            if pt_coord is not None and pt_coord.text:
                try:
                    parts = [float(x) for x in pt_coord.text.strip().split(",")[:2]]
                    features.append({"name": name, "geometry": Point(parts[0], parts[1])})
                    continue
                except Exception:
                    pass

            # 2. LineString
            ls_coord = p.find(".//{http://www.opengis.net/kml/2.2}LineString/{http://www.opengis.net/kml/2.2}coordinates") or p.find(".//LineString/coordinates")
            if ls_coord is not None and ls_coord.text:
                try:
                    pts = []
                    for c_str in ls_coord.text.strip().split():
                        coords = [float(x) for x in c_str.strip().split(",")[:2]]
                        pts.append((coords[0], coords[1]))
                    if len(pts) >= 2:
                        features.append({"name": name, "geometry": LineString(pts)})
                        continue
                except Exception:
                    pass

            # 3. Polygon
            poly_coord = p.find(".//{http://www.opengis.net/kml/2.2}Polygon//{http://www.opengis.net/kml/2.2}coordinates") or p.find(".//Polygon//coordinates")
            if poly_coord is not None and poly_coord.text:
                try:
                    pts = []
                    for c_str in poly_coord.text.strip().split():
                        coords = [float(x) for x in c_str.strip().split(",")[:2]]
                        pts.append((coords[0], coords[1]))
                    if len(pts) >= 3:
                        features.append({"name": name, "geometry": Polygon(pts)})
                        continue
                except Exception:
                    pass

        if features:
            return gpd.GeoDataFrame(features, crs="EPSG:4326")
        return gpd.GeoDataFrame(columns=["name", "geometry"], crs="EPSG:4326")

    @classmethod
    def process_shapefile_zip(cls, zip_path: Path) -> Tuple[gpd.GeoDataFrame, str]:
        """
        Safely extract and read a Shapefile ZIP archive.
        Verifies .shp, .shx, and .dbf files, detects CRS, and returns a GeoDataFrame.
        """
        with tempfile.TemporaryDirectory() as tmp_extract_dir:
            extract_dir = Path(tmp_extract_dir)

            # Safely extract files (preventing Zip Slip)
            safe_extract_zip(zip_path, extract_dir)

            # Verify mandatory Shapefile components (.shp, .shx, .dbf)
            shp_path, _ = verify_shapefile_components(extract_dir)

            try:
                gdf = gpd.read_file(shp_path)
            except Exception as e:
                raise CorruptedFileError(f"Failed to read Shapefile: {e}")

            # Resolve CRS
            source_crs = gdf.crs
            if source_crs is None:
                # Check if coordinates match geographic range
                if not gdf.empty and gdf.geometry.notnull().any():
                    total_bounds = gdf.total_bounds
                    if -180.0 <= total_bounds[0] <= 180.0 and -90.0 <= total_bounds[1] <= 90.0:
                        logger.warning("Shapefile lacks .prj metadata. Coordinates match geographic bounds, defaulting to EPSG:4326.")
                        gdf.set_crs("EPSG:4326", inplace=True)
                        source_crs = gdf.crs

            crs_str = crs_service.get_crs_name(source_crs)
            # Make a copy in memory so cleanup of tmp directory does not affect gdf
            gdf_copy = gdf.copy(deep=True)

        return gdf_copy, crs_str


file_processor_service = FileProcessorService()
