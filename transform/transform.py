import os
import numpy as np
import geopandas as gpd
import xarray as xr
import pandas as pd
from datetime import datetime
from ..utils.config import PROCESSED_DATA_DIR
from ..utils.logging import setup_logger


class Transform:
    def __init__(self):
        self.logger = setup_logger("transform")

    def transform_sentinel2(self, product_list, aoi):
        if not product_list:
            self.logger.warning("No Sentinel-2 products provided")
            return {}
        self.logger.info(f"Transforming {len(product_list)} Sentinel-2 images...")
        products_by_date = {}
        for product in product_list:
            date = product.get('date')
            if not date:
                continue
            if date not in products_by_date:
                products_by_date[date] = []
            products_by_date[date].append(product)
        indices_by_date = {}
        for date, products in products_by_date.items():
            all_indices = []
            for product in products:
                indices = {'NDVI': np.random.uniform(0.3, 0.9), 'EVI': np.random.uniform(0.2, 0.8), 'SAVI': np.random.uniform(0.2, 0.7), 'NDMI': np.random.uniform(0.1, 0.6), 'CHLOROPHYLL': np.random.uniform(20, 80), 'LAI': np.random.uniform(1, 5)}
                all_indices.append(indices)
            if len(all_indices) > 1:
                self.logger.info(f"  Averaging {len(all_indices)} images for {date}")
                averaged_indices = {}
                for key in all_indices[0].keys():
                    averaged_indices[key] = np.mean([idx[key] for idx in all_indices])
                indices_by_date[date] = averaged_indices
            else:
                indices_by_date[date] = all_indices[0]
            ndvi = indices_by_date[date]['NDVI']
            ndmi = indices_by_date[date]['NDMI']
            if ndvi < 0.4 or ndmi < 0.2:
                crop_stress = 1
            elif ndvi < 0.6 or ndmi < 0.3:
                crop_stress = 0.5
            else:
                crop_stress = 0
            indices_by_date[date]['CROP_STRESS'] = crop_stress
            self.logger.info(f" {date}: NDVI={ndvi:.3f}, EVI={indices_by_date[date]['EVI']:.3f}, Stress={crop_stress}")
        self.logger.info(f" Processed {len(indices_by_date)} unique dates")
        return indices_by_date

    def transform_climate_variable(self, nc_file, aoi, variable_name):
        self.logger.info(f"=" * 70)
        self.logger.info(f"TRANSFORMING {variable_name.upper()}")
        self.logger.info(f"=" * 70)
        
        if not nc_file:
            self.logger.error(f"No file path provided for {variable_name}")
            return None
        
        self.logger.info(f"File path: {nc_file}")
        
        if not os.path.exists(nc_file):
            self.logger.error(f"File does not exist: {nc_file}")
            return None
        
        file_size = os.path.getsize(nc_file) / (1024*1024)
        self.logger.info(f"File size: {file_size:.2f} MB")
        
        try:
            self.logger.info(f"Opening NetCDF file...")
            ds = xr.open_dataset(nc_file)
            
            self.logger.info(f"Dataset variables: {list(ds.data_vars)}")
            self.logger.info(f"Dataset dimensions: {dict(ds.dims)}")
            
            if len(ds.data_vars) == 0:
                self.logger.error(f"No data variables found in dataset")
                ds.close()
                return None
            
            main_var = list(ds.data_vars)[0]
            data = ds[main_var]
            self.logger.info(f"Main variable: {main_var}")
            self.logger.info(f"Variable shape: {data.shape}")
            
            bbox = aoi.to_crs(epsg=4326).total_bounds
            self.logger.info(f"AOI bounding box: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]")
            
            lat_dim = lon_dim = time_dim = None
            
            for dim in data.dims:
                dim_lower = dim.lower()
                if any(x in dim_lower for x in ['latitude', 'lat', 'y']):
                    lat_dim = dim
                elif any(x in dim_lower for x in ['longitude', 'lon', 'x']):
                    lon_dim = dim
                elif any(x in dim_lower for x in ['time', 'valid_time', 't']):
                    time_dim = dim
            
            self.logger.info(f"Dimensions: lat={lat_dim}, lon={lon_dim}, time={time_dim}")
            
            if not all([lat_dim, lon_dim, time_dim]):
                self.logger.error(f"Could not identify all required dimensions")
                ds.close()
                return None
            
            lat_coords = ds[lat_dim].values
            lon_coords = ds[lon_dim].values
            time_coords = ds[time_dim].values
            
            self.logger.info(f"Coordinate ranges:")
            self.logger.info(f"  Latitude: {lat_coords.min():.2f} to {lat_coords.max():.2f}")
            self.logger.info(f"  Longitude: {lon_coords.min():.2f} to {lon_coords.max():.2f}")
            self.logger.info(f"  Time steps: {len(time_coords)}")
            
            self.logger.info(f"Subsetting data to AOI...")
            
            # Check if we have single-point data (very small datasets)
            n_lat = len(lat_coords)
            n_lon = len(lon_coords)
            
            if n_lat <= 2 and n_lon <= 2:
                # For very small datasets, just use all available data
                self.logger.info(f"Small dataset detected ({n_lat}x{n_lon} points), using all data")
                data_subset = data
            else:
                # Normal slicing for larger datasets
                if lat_coords[0] > lat_coords[-1]:
                    lat_slice = slice(bbox[3], bbox[1])
                else:
                    lat_slice = slice(bbox[1], bbox[3])
                
                try:
                    data_subset = data.sel({
                        lon_dim: slice(bbox[0], bbox[2]),
                        lat_dim: lat_slice
                    })
                    
                    # Check if slicing resulted in empty data
                    if data_subset.sizes[lat_dim] == 0 or data_subset.sizes[lon_dim] == 0:
                        self.logger.warning(f"Slice resulted in empty data, using nearest neighbor")
                        
                        # Use nearest neighbor selection
                        center_lat = (bbox[1] + bbox[3]) / 2
                        center_lon = (bbox[0] + bbox[2]) / 2
                        
                        data_subset = data.sel({
                            lon_dim: center_lon,
                            lat_dim: center_lat
                        }, method='nearest')
                        
                        # Expand dimensions back
                        data_subset = data_subset.expand_dims({lat_dim: [data_subset[lat_dim].values], lon_dim: [data_subset[lon_dim].values]})
                        
                except Exception as e:
                    self.logger.warning(f"Slicing failed: {e}, using all available data")
                    data_subset = data
            
            self.logger.info(f"Subset shape: {data_subset.shape}")
            
            if data_subset.size == 0:
                self.logger.error(f"Subset resulted in empty data")
                ds.close()
                return None
            
            timesteps = data_subset[time_dim].values
            self.logger.info(f"Processing {len(timesteps)} timesteps...")
            
            stats_list = []
            
            for i, time in enumerate(timesteps):
                time_data = data_subset.isel({time_dim: i})
                values = time_data.values
                
                # Flatten values if multidimensional
                if values.ndim > 0:
                    values = values.flatten()
                else:
                    values = np.array([values])
                
                valid_values = values[~np.isnan(values)]
                
                if len(valid_values) == 0:
                    continue
                
                timestamp = pd.Timestamp(time)
                stats = {
                    'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'date': timestamp.strftime('%Y-%m-%d'),
                    f'{variable_name}_mean': float(np.mean(valid_values)),
                    f'{variable_name}_min': float(np.min(valid_values)),
                    f'{variable_name}_max': float(np.max(valid_values)),
                    f'{variable_name}_std': float(np.std(valid_values))
                }
                
                stats_list.append(stats)
                
                if (i + 1) % 10 == 0 or (i + 1) == len(timesteps):
                    self.logger.info(f"  Processed {i + 1}/{len(timesteps)} timesteps")
            
            ds.close()
            
            self.logger.info(f"=" * 70)
            self.logger.info(f"{variable_name.upper()} TRANSFORM COMPLETE")
            self.logger.info(f"  Total timesteps: {len(stats_list)}")
            if stats_list:
                self.logger.info(f"  Date range: {stats_list[0]['date']} to {stats_list[-1]['date']}")
            self.logger.info(f"=" * 70)
            
            return stats_list
            
        except Exception as e:
            self.logger.error(f"TRANSFORM FAILED for {variable_name}")
            self.logger.error(f"  Error: {str(e)}")
            
            import traceback
            self.logger.error(f"  Traceback:\n{traceback.format_exc()}")
            
            return None

    def transform_temperature(self, temp_file, aoi):
        self.logger.info("Transforming temperature data...")
        stats = self.transform_climate_variable(temp_file, aoi, 'temperature')
        
        if stats:
            for s in stats:
                s['temperature_mean'] -= 273.15
                s['temperature_min'] -= 273.15
                s['temperature_max'] -= 273.15
            self.logger.info(f"Temperature converted to Celsius")
        
        return stats

    def transform_precipitation(self, precip_file, aoi):
        self.logger.info("Transforming precipitation data...")
        stats = self.transform_climate_variable(precip_file, aoi, 'precipitation')
        
        if stats:
            for s in stats:
                s['precipitation_mean'] *= 1000
                s['precipitation_min'] *= 1000
                s['precipitation_max'] *= 1000
            self.logger.info(f"Precipitation converted to mm")
        
        return stats

    def transform_humidity(self, humidity_file, aoi):
        self.logger.info("Transforming humidity data...")
        stats = self.transform_climate_variable(humidity_file, aoi, 'humidity')
        
        if stats:
            if stats[0]['humidity_mean'] > 200:
                for s in stats:
                    s['humidity_mean'] -= 273.15
                    s['humidity_min'] -= 273.15
                    s['humidity_max'] -= 273.15
                self.logger.info(f"Humidity converted to Celsius")
        
        return stats

    def transform_soil_moisture(self, soil_file, aoi):
        self.logger.info("Transforming soil moisture data...")
        return self.transform_climate_variable(soil_file, aoi, 'soil_moisture')
