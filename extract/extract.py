"""
Unified data extraction class for the ETL package.
"""

import os
import zipfile
import requests
import geopandas as gpd
import cdsapi
from datetime import datetime
from ..utils.config import RAW_DATA_DIR, START_DATE, END_DATE, ERA5_VARIABLES, CDSE_USERNAME, CDSE_PASSWORD
from ..utils.logging import setup_logger


class Extract:
    def __init__(self, cdse_token: str = None):
        self.cdse_token = cdse_token
        self.cdse_username = CDSE_USERNAME
        self.cdse_password = CDSE_PASSWORD
        self.logger = setup_logger("extract")

    def _refresh_token(self):
        """Refresh CDSE token if expired."""
        self.logger.info("🔄 Refreshing CDSE token...")
        auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "username": self.cdse_username,
            "password": self.cdse_password,
            "client_id": "cdse-public",
        }
        try:
            response = requests.post(auth_url, data=data, timeout=30)
            response.raise_for_status()
            self.cdse_token = response.json()["access_token"]
            self.logger.info(" Token refreshed")
        except Exception as e:
            self.logger.error(f"Failed to refresh token: {e}")

    def get_aoi(self, zip_path: str):
        self.logger.info(f"Extracting AOI shapefile from {os.path.basename(zip_path)}...")
        shp_files = []
        for root, _, files in os.walk(RAW_DATA_DIR):
            shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])
        if not shp_files:
            if not os.path.exists(zip_path):
                raise FileNotFoundError(f"AOI ZIP file not found: {zip_path}")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(RAW_DATA_DIR)
            for root, _, files in os.walk(RAW_DATA_DIR):
                shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])
        if not shp_files:
            raise FileNotFoundError("No .shp file found")
        aoi = gpd.read_file(shp_files[0])
        bbox = aoi.to_crs(epsg=4326).total_bounds
        self.logger.info(f"AOI extracted: {os.path.basename(shp_files[0])}")
        self.logger.info(f"   Bounding box: {bbox}")
        return aoi, bbox

    def get_sentinel2(self, bbox, max_images=32):
        if not self.cdse_token:
            self.logger.warning("CDSE token missing")
            return []
        
        existing_s2_folders = []
        for item in os.listdir(RAW_DATA_DIR):
            item_path = os.path.join(RAW_DATA_DIR, item)
            if os.path.isdir(item_path) and item.startswith('S2') and item.endswith('.SAFE'):
                try:
                    date_str = item.split('_')[2].split('T')[0]
                    date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                    existing_s2_folders.append({'path': item_path, 'date': date, 'name': item})
                except:
                    pass
        
        if existing_s2_folders:
            self.logger.info(f"Found {len(existing_s2_folders)} existing Sentinel-2 products")
            return existing_s2_folders

        self.logger.info(f"Searching for Sentinel-2 products...")
        search_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        bbox_str = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"
        
        # Search for images covering the ENTIRE time period
        params = {
            "$filter": f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_str}') and ContentDate/Start gt {START_DATE} and ContentDate/Start lt {END_DATE}",
            "$orderby": "ContentDate/Start asc",  # Get oldest first for better coverage
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
            self.logger.info(f"Found {len(products)} products")
            
            downloaded_products = []
            
            for idx, product in enumerate(products):
                product_id = product['Id']
                product_name = product['Name']
                
                try:
                    date_str = product_name.split('_')[2].split('T')[0]
                    product_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                except:
                    product_date = None
                
                self.logger.info(f"\n[{idx+1}/{len(products)}] {product_name} (Date: {product_date})")
                
                download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
                headers = {"Authorization": f"Bearer {self.cdse_token}"}
                product_zip = os.path.join(RAW_DATA_DIR, f"{product_name}.zip")
                
                try:
                    with requests.get(download_url, headers=headers, stream=True, timeout=600) as r:
                        if r.status_code == 401:
                            self.logger.warning("Token expired, refreshing...")
                            self._refresh_token()
                            headers = {"Authorization": f"Bearer {self.cdse_token}"}
                            r = requests.get(download_url, headers=headers, stream=True, timeout=600)
                        
                        r.raise_for_status()
                        total_size = int(r.headers.get('content-length', 0))
                        
                        with open(product_zip, 'wb') as f:
                            downloaded = 0
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0 and downloaded % (50 * 1024 * 1024) == 0:
                                    self.logger.info(f"  {(downloaded/total_size)*100:.1f}%")
                    
                    self.logger.info("  Extracting...")
                    product_folder = os.path.join(RAW_DATA_DIR, product_name)
                    with zipfile.ZipFile(product_zip, 'r') as zip_ref:
                        zip_ref.extractall(RAW_DATA_DIR)
                    os.remove(product_zip)
                    
                    self.logger.info(f" Done")
                    downloaded_products.append({'path': product_folder, 'date': product_date, 'name': product_name})
                    
                except Exception as e:
                    self.logger.error(f" Error: {e}")
                    if os.path.exists(product_zip):
                        os.remove(product_zip)
            
            return downloaded_products
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return []

    def _download_era5_variable(self, variable_name: str, variable_code: str, bbox: list):
        start_date = datetime.fromisoformat(START_DATE.replace('Z', '+00:00'))
        output_file = os.path.join(RAW_DATA_DIR, f"era5_{variable_name}_{start_date.strftime('%Y%m%d')}.nc")
        
        if os.path.exists(output_file):
            self.logger.info(f"ERA5 {variable_name} exists")
            return output_file
        
        self.logger.info(f"Downloading ERA5 {variable_name}...")
        try:
            c = cdsapi.Client()
            end_date = datetime.fromisoformat(END_DATE.replace('Z', '+00:00'))
            days = [f"{d:02d}" for d in range(start_date.day, min(end_date.day + 1, 32))]
            
            request = {
                'product_type': 'reanalysis',
                'variable': variable_code,
                'year': str(start_date.year),
                'month': f"{start_date.month:02d}",
                'day': days,
                'time': ['00:00', '06:00', '12:00', '18:00'],
                'area': [bbox[3], bbox[0], bbox[1], bbox[2]],
                'format': 'netcdf',
            }
            
            c.retrieve('reanalysis-era5-single-levels', request, output_file)
            self.logger.info(f"Downloaded")
            return output_file
        except Exception as e:
            self.logger.error(f"Error: {e}")
            return None

    def get_temperature(self, bbox):
        return self._download_era5_variable('temperature', ERA5_VARIABLES['temperature'], bbox)

    def get_precipitation(self, bbox):
        return self._download_era5_variable('precipitation', ERA5_VARIABLES['precipitation'], bbox)

    def get_humidity(self, bbox):
        return self._download_era5_variable('humidity', ERA5_VARIABLES['humidity'], bbox)

    def get_soil_moisture(self, bbox):
        return self._download_era5_variable('soil_moisture', ERA5_VARIABLES['soil_moisture'], bbox)

    def get_all_climate_data(self, bbox):
        self.logger.info("📊 Downloading climate data...")
        return {
            'temperature': self.get_temperature(bbox),
            'precipitation': self.get_precipitation(bbox),
            'humidity': self.get_humidity(bbox),
            'soil_moisture': self.get_soil_moisture(bbox)
        }
