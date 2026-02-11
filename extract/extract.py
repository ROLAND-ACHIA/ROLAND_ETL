import os
import zipfile
import requests
import geopandas as gpd
import cdsapi
from datetime import datetime, timedelta
from ..utils.config import RAW_DATA_DIR, ERA5_VARIABLES, CDSE_USERNAME, CDSE_PASSWORD
from ..utils.logging import setup_logger

class Extract:
    def __init__(self, cdse_token: str = None, start_date: str = None, end_date: str = None):
        self.cdse_token = cdse_token
        self.cdse_username = CDSE_USERNAME
        self.cdse_password = CDSE_PASSWORD
        self.logger = setup_logger("extract")
        self.start_date = start_date
        self.end_date = end_date
        
    def _refresh_token(self):
        """Refresh CDSE token if expired."""
        self.logger.info("Refreshing CDSE token...")
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
            self.logger.info("Token refreshed")
        except Exception as e:
            self.logger.error(f"Failed to refresh token: {e}")
    
    def get_aoi(self, shapefile_path: str):
        """
        Load Area of Interest from shapefile.
        Args:
            shapefile_path: Path to the .shp file (already extracted)
        Returns:
            tuple: (GeoDataFrame, bounding box)
        """
        self.logger.info(f"Loading AOI from {os.path.basename(shapefile_path)}...")
        
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")
        
        if not shapefile_path.endswith('.shp'):
            raise ValueError(f"Expected .shp file, got: {shapefile_path}")
        
        aoi = gpd.read_file(shapefile_path)
        bbox = aoi.to_crs(epsg=4326).total_bounds
        
        self.logger.info(f"AOI loaded: {os.path.basename(shapefile_path)}")
        self.logger.info(f"   Bounding box: {bbox}")
        
        return aoi, bbox
    
    def get_sentinel2(self, bbox, max_images=500):
        if not self.cdse_token:
            self.logger.warning("CDSE token missing")
            return []
        
        start_date_obj = datetime.fromisoformat((self.start_date if self.start_date else "2024-12-01T00:00:00Z").replace('Z', '+00:00'))
        end_date_obj = datetime.fromisoformat((self.end_date if self.end_date else "2024-12-31T23:59:59Z").replace('Z', '+00:00'))
        
        # Check for existing products
        existing_s2_folders = []
        existing_product_names = set()
        for item in os.listdir(RAW_DATA_DIR):
            item_path = os.path.join(RAW_DATA_DIR, item)
            if os.path.isdir(item_path) and item.startswith('S2') and item.endswith('.SAFE'):
                try:
                    date_str = item.split('_')[2].split('T')[0]
                    date = datetime.strptime(date_str, '%Y%m%d')
                    
                    if start_date_obj.date() <= date.date() <= end_date_obj.date():
                        date_formatted = date.strftime('%Y-%m-%d')
                        existing_s2_folders.append({'path': item_path, 'date': date_formatted, 'name': item})
                        existing_product_names.add(item)
                except:
                    pass
        
        if existing_s2_folders:
            self.logger.info(f"Found {len(existing_s2_folders)} existing Sentinel-2 products in date range")
        
        # Always search for new products
        self.logger.info(f"Searching for Sentinel-2 products from {self.start_date} to {self.end_date}...")
        search_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        bbox_str = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"
        
        start_date = self.start_date if self.start_date else "2024-12-01T00:00:00Z"
        end_date = self.end_date if self.end_date else "2024-12-31T23:59:59Z"
        
        params = {
            "$filter": f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_str}') and ContentDate/Start gt {start_date} and ContentDate/Start lt {end_date}",
            "$orderby": "ContentDate/Start asc",
            "$top": max_images
        }
        
        try:
            response = requests.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            results = response.json()
            
            if not results.get('value'):
                self.logger.warning(f"No Sentinel-2 products found for date range {start_date} to {end_date}")
                if existing_s2_folders:
                    self.logger.info(f"Using {len(existing_s2_folders)} existing products")
                    return existing_s2_folders
                return []
            
            products = results['value']
            self.logger.info(f"Found {len(products)} total products available")
            
            # Filter out products that already exist
            new_products = [p for p in products if p['Name'] not in existing_product_names]
            self.logger.info(f"New products to download: {len(new_products)}")
            
            if len(new_products) == 0:
                self.logger.info(f"All products already downloaded, using {len(existing_s2_folders)} existing products")
                return existing_s2_folders
            
            downloaded_products = []
            
            for idx, product in enumerate(new_products):
                product_id = product['Id']
                product_name = product['Name']
                
                try:
                    date_str = product_name.split('_')[2].split('T')[0]
                    product_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                except:
                    product_date = None
                
                self.logger.info(f"[{idx+1}/{len(new_products)}] Downloading {product_name} (Date: {product_date})")
                
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
                    
                    self.logger.info(f"  Done")
                    downloaded_products.append({'path': product_folder, 'date': product_date, 'name': product_name})
                    
                except Exception as e:
                    self.logger.error(f"  Error: {e}")
                    if os.path.exists(product_zip):
                        os.remove(product_zip)
            
            # Combine existing and newly downloaded products
            all_products = existing_s2_folders + downloaded_products
            self.logger.info(f"Total Sentinel-2 products available: {len(all_products)} ({len(existing_s2_folders)} existing + {len(downloaded_products)} new)")
            return all_products
            
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            if existing_s2_folders:
                self.logger.info(f"Returning {len(existing_s2_folders)} existing products despite search error")
                return existing_s2_folders
            return []
    
    def _download_era5_variable(self, variable_name: str, variable_code: str, bbox: list):
        start_date_obj = datetime.fromisoformat((self.start_date if self.start_date else "2024-12-01T00:00:00Z").replace('Z', '+00:00'))
        end_date_obj = datetime.fromisoformat((self.end_date if self.end_date else "2024-12-31T23:59:59Z").replace('Z', '+00:00'))
        
        # Create location-specific filename based on bounding box
        # Round bbox to 2 decimals and encode in filename
        bbox_str = f"{int(bbox[0]*100)}_{int(bbox[1]*100)}_{int(bbox[2]*100)}_{int(bbox[3]*100)}"
        output_file = os.path.join(RAW_DATA_DIR, f"era5_{variable_name}_{start_date_obj.strftime('%Y%m%d')}_{end_date_obj.strftime('%Y%m%d')}_{bbox_str}.nc")
        
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / (1024*1024)
            self.logger.info(f"ERA5 {variable_name} already exists ({file_size:.2f} MB)")
            print(f"[EXTRACT] ERA5 {variable_name} file exists: {output_file}")
            return output_file
        
        self.logger.info(f"Downloading ERA5 {variable_name}...")
        self.logger.info(f"  Bounding box: {bbox}")
        print(f"[EXTRACT] Downloading ERA5 {variable_name} from CDS API...")
        print(f"[EXTRACT] Bounding box: {bbox}")
        
        try:
            c = cdsapi.Client()
            
            current_date = start_date_obj
            years = set()
            months = set()
            days = set()
            
            while current_date <= end_date_obj:
                years.add(str(current_date.year))
                months.add(f"{current_date.month:02d}")
                days.add(f"{current_date.day:02d}")
                current_date += timedelta(days=1)
            
            years = sorted(list(years))
            months = sorted(list(months))
            days = sorted(list(days))
            
            request = {
                'product_type': 'reanalysis',
                'variable': variable_code,
                'year': years,
                'month': months,
                'day': days,
                'time': ['00:00', '06:00', '12:00', '18:00'],
                'area': [bbox[3], bbox[0], bbox[1], bbox[2]],
                'format': 'netcdf',
            }
            
            print(f"[EXTRACT] Submitting CDS request for {variable_name}...")
            c.retrieve('reanalysis-era5-single-levels', request, output_file)
            
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024*1024)
                self.logger.info(f"Downloaded successfully ({file_size:.2f} MB)")
                print(f"[EXTRACT] Downloaded {variable_name}: {output_file} ({file_size:.2f} MB)")
                return output_file
            else:
                self.logger.error(f"Download completed but file not found!")
                print(f"[EXTRACT] ERROR: File not found after download")
                return None
                
        except Exception as e:
            self.logger.error(f"ERA5 download failed for {variable_name}")
            self.logger.error(f"Error: {str(e)}")
            print(f"[EXTRACT] ERROR downloading {variable_name}: {e}")
            import traceback
            print(traceback.format_exc())
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
        self.logger.info("Downloading climate data...")
        print("[EXTRACT] Starting climate data download...")
        
        result = {
            'temperature': self.get_temperature(bbox),
            'precipitation': self.get_precipitation(bbox),
            'humidity': self.get_humidity(bbox),
            'soil_moisture': self.get_soil_moisture(bbox)
        }
        
        print(f"[EXTRACT] Climate download results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        return result
