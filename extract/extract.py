"""
Unified data extraction class for the ETL package.

Handles:
- AOI shapefile extraction
- Sentinel-2 imagery download (CDSE) - multiple images
- ERA5 climate data download (CDS API): temperature, precipitation, humidity, soil moisture
"""

import os
import zipfile
import requests
import geopandas as gpd
import cdsapi
from datetime import datetime
from ..utils.config import RAW_DATA_DIR, START_DATE, END_DATE, ERA5_VARIABLES
from ..utils.logging import setup_logger


class Extract:
    """
    Main data extraction handler.

    Attributes
    ----------
    cdse_token : str
        Access token for CDSE platform (Sentinel-2).
    """

    def __init__(self, cdse_token: str = None):
        self.cdse_token = cdse_token
        self.logger = setup_logger("extract")

    # ------------------------------------------------------------------
    # AOI EXTRACTION
    # ------------------------------------------------------------------
    def get_aoi(self, zip_path: str):
        """
        Extracts an AOI shapefile from a ZIP archive and loads it as GeoDataFrame.

        Parameters
        ----------
        zip_path : str
            Path to AOI ZIP file.

        Returns
        -------
        tuple
            (aoi_gdf, bbox) where bbox = [minx, miny, maxx, maxy]
        """
        self.logger.info(f"Extracting AOI shapefile from {os.path.basename(zip_path)}...")

        shp_files = []
        for root, _, files in os.walk(RAW_DATA_DIR):
            shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])

        if not shp_files:
            if not os.path.exists(zip_path):
                raise FileNotFoundError(f"AOI ZIP file not found: {zip_path}")
            
            self.logger.info(f"Extracting {zip_path} to {RAW_DATA_DIR}...")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(RAW_DATA_DIR)
            
            for root, _, files in os.walk(RAW_DATA_DIR):
                shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])

        if not shp_files:
            raise FileNotFoundError("No .shp file found after extracting ZIP")

        aoi = gpd.read_file(shp_files[0])
        bbox = aoi.to_crs(epsg=4326).total_bounds
        self.logger.info(f"✅ AOI extracted successfully: {os.path.basename(shp_files[0])}")
        self.logger.info(f"   Bounding box: {bbox}")
        return aoi, bbox

    # ------------------------------------------------------------------
    # SENTINEL-2 EXTRACTION (MULTIPLE IMAGES)
    # ------------------------------------------------------------------
    def get_sentinel2(self, bbox, max_images=10):
        """
        Downloads multiple Sentinel-2 images for the given bounding box and time range.

        Parameters
        ----------
        bbox : list or tuple
            [minx, miny, maxx, maxy] of AOI.
        max_images : int
            Maximum number of images to download (default: 10 for ~10 days)

        Returns
        -------
        list
            List of dictionaries with 'path' and 'date' for each product
        """
        if not self.cdse_token:
            self.logger.warning("CDSE token missing. Skipping Sentinel-2 extraction.")
            return []

        # Check for existing Sentinel-2 data
        existing_s2_folders = []
        for item in os.listdir(RAW_DATA_DIR):
            item_path = os.path.join(RAW_DATA_DIR, item)
            if os.path.isdir(item_path) and item.startswith('S2') and item.endswith('.SAFE'):
                # Extract date from product name (format: S2X_MSIL2A_YYYYMMDDTHHMMSS_...)
                try:
                    date_str = item.split('_')[2].split('T')[0]
                    date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                    existing_s2_folders.append({'path': item_path, 'date': date, 'name': item})
                except:
                    existing_s2_folders.append({'path': item_path, 'date': None, 'name': item})
        
        if existing_s2_folders:
            self.logger.info(f"✅ Found {len(existing_s2_folders)} existing Sentinel-2 products")
            for product in existing_s2_folders:
                self.logger.info(f"   - {product['name']} (Date: {product['date']})")
            self.logger.info("   Skipping download.")
            return existing_s2_folders

        self.logger.info(f"Searching for up to {max_images} Sentinel-2 products on CDSE...")
        
        search_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        bbox_str = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"
        
        params = {
            "$filter": f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_str}') and ContentDate/Start gt {START_DATE} and ContentDate/Start lt {END_DATE}",
            "$orderby": "ContentDate/Start desc",
            "$top": max_images
        }
        
        try:
            response = requests.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            results = response.json()
            
            if not results.get('value'):
                self.logger.warning("No Sentinel-2 products found")
                return []
            
            products = results['value']
            self.logger.info(f"Found {len(products)} Sentinel-2 products")
            
            downloaded_products = []
            
            for idx, product in enumerate(products):
                product_id = product['Id']
                product_name = product['Name']
                
                # Extract date from product
                try:
                    date_str = product_name.split('_')[2].split('T')[0]
                    product_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                except:
                    product_date = None
                
                self.logger.info(f"Downloading {idx+1}/{len(products)}: {product_name}")
                
                download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
                headers = {"Authorization": f"Bearer {self.cdse_token}"}
                product_zip = os.path.join(RAW_DATA_DIR, f"{product_name}.zip")
                
                self.logger.info(f"Downloading to {product_zip}...")
                
                with requests.get(download_url, headers=headers, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    
                    with open(product_zip, 'wb') as f:
                        downloaded = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if downloaded % (50 * 1024 * 1024) == 0:  # Log every 50MB
                                    self.logger.info(f"Downloaded: {percent:.1f}%")
                
                self.logger.info("Download complete. Extracting...")
                
                product_folder = os.path.join(RAW_DATA_DIR, product_name)
                with zipfile.ZipFile(product_zip, 'r') as zip_ref:
                    zip_ref.extractall(product_folder)
                
                os.remove(product_zip)
                
                self.logger.info(f"✅ Extracted to {product_folder}")
                
                downloaded_products.append({
                    'path': product_folder,
                    'date': product_date,
                    'name': product_name
                })
            
            return downloaded_products
            
        except Exception as e:
            self.logger.error(f"Error downloading Sentinel-2 data: {e}")
            return []

    # ------------------------------------------------------------------
    # ERA5 CLIMATE DATA EXTRACTION
    # ------------------------------------------------------------------
    def _download_era5_variable(self, variable_name: str, variable_code: str, bbox: list):
        """
        Generic method to download ERA5 variables from CDS.

        Parameters
        ----------
        variable_name : str
            Human-readable name (e.g., 'temperature', 'precipitation')
        variable_code : str
            ERA5 variable code (e.g., '2m_temperature')
        bbox : list
            [minx, miny, maxx, maxy] of AOI

        Returns
        -------
        str or None
            Path to downloaded file, or None if failed
        """
        start_date = datetime.fromisoformat(START_DATE.replace('Z', '+00:00'))
        
        output_file = os.path.join(RAW_DATA_DIR, f"era5_{variable_name}_{start_date.strftime('%Y%m%d')}.nc")
        
        if os.path.exists(output_file):
            self.logger.info(f"✅ ERA5 {variable_name} already exists: {os.path.basename(output_file)}")
            self.logger.info("   Skipping download.")
            return output_file
        
        self.logger.info(f"Downloading ERA5 {variable_name} from CDS...")
        self.logger.info("🔑 Using CDS API credentials from ~/.cdsapirc")
        
        try:
            c = cdsapi.Client()
            
            request = {
                'product_type': 'reanalysis',
                'variable': variable_code,
                'year': str(start_date.year),
                'month': f"{start_date.month:02d}",
                'day': [f"{d:02d}" for d in range(start_date.day, min(start_date.day + 10, 32))],
                'time': ['00:00', '06:00', '12:00', '18:00'],
                'area': [bbox[3], bbox[0], bbox[1], bbox[2]],
                'format': 'netcdf',
            }
            
            self.logger.info(f"Requesting {variable_name} for: {start_date.strftime('%Y-%m-%d')}")
            
            c.retrieve('reanalysis-era5-single-levels', request, output_file)
            
            self.logger.info(f"✅ ERA5 {variable_name} downloaded to {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"Error downloading {variable_name}: {e}")
            return None

    def get_temperature(self, bbox):
        """Download ERA5 temperature data."""
        return self._download_era5_variable('temperature', ERA5_VARIABLES['temperature'], bbox)

    def get_precipitation(self, bbox):
        """Download ERA5 precipitation data."""
        return self._download_era5_variable('precipitation', ERA5_VARIABLES['precipitation'], bbox)

    def get_humidity(self, bbox):
        """Download ERA5 humidity data (dewpoint temperature)."""
        return self._download_era5_variable('humidity', ERA5_VARIABLES['humidity'], bbox)

    def get_soil_moisture(self, bbox):
        """Download ERA5 soil moisture data."""
        return self._download_era5_variable('soil_moisture', ERA5_VARIABLES['soil_moisture'], bbox)

    def get_all_climate_data(self, bbox):
        """
        Download all climate variables (temperature, precipitation, humidity, soil moisture).

        Parameters
        ----------
        bbox : list
            [minx, miny, maxx, maxy] of AOI

        Returns
        -------
        dict
            Dictionary with variable names as keys and file paths as values
        """
        self.logger.info("📊 Downloading all climate variables...")
        
        climate_data = {
            'temperature': self.get_temperature(bbox),
            'precipitation': self.get_precipitation(bbox),
            'humidity': self.get_humidity(bbox),
            'soil_moisture': self.get_soil_moisture(bbox)
        }
        
        self.logger.info("✅ All climate data extraction complete")
        return climate_data
