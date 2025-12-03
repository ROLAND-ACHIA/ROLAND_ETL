"""
Transformation module for processing Sentinel-2 and ERA5 climate data.
"""

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
        """
        Computes vegetation indices from multiple Sentinel-2 images.
        If multiple images exist for the same date, averages them.
        """
        if not product_list:
            self.logger.warning("No Sentinel-2 products provided")
            return {}

        self.logger.info(f"Transforming {len(product_list)} Sentinel-2 images...")
        
        # Group products by date
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
            # If multiple images for same date, compute indices for each and average
            all_indices = []
            
            for product in products:
                # Mock indices (replace with actual band calculations later)
                indices = {
                    'NDVI': np.random.uniform(0.3, 0.9),
                    'EVI': np.random.uniform(0.2, 0.8),
                    'SAVI': np.random.uniform(0.2, 0.7),
                    'NDMI': np.random.uniform(0.1, 0.6),
                    'CHLOROPHYLL': np.random.uniform(20, 80),
                    'LAI': np.random.uniform(1, 5),
                }
                all_indices.append(indices)
            
            # Average indices if multiple images for same date
            if len(all_indices) > 1:
                self.logger.info(f"  Averaging {len(all_indices)} images for {date}")
                averaged_indices = {}
                for key in all_indices[0].keys():
                    averaged_indices[key] = np.mean([idx[key] for idx in all_indices])
                indices_by_date[date] = averaged_indices
            else:
                indices_by_date[date] = all_indices[0]
            
            # Calculate crop stress
            ndvi = indices_by_date[date]['NDVI']
            ndmi = indices_by_date[date]['NDMI']
            
            if ndvi < 0.4 or ndmi < 0.2:
                crop_stress = 1  # High stress
            elif ndvi < 0.6 or ndmi < 0.3:
                crop_stress = 0.5  # Moderate stress
            else:
                crop_stress = 0  # Low stress
            
            indices_by_date[date]['CROP_STRESS'] = crop_stress
            
            self.logger.info(f" {date}: NDVI={ndvi:.3f}, EVI={indices_by_date[date]['EVI']:.3f}, Stress={crop_stress}")
        
        self.logger.info(f" Processed {len(indices_by_date)} unique dates")
        return indices_by_date

    def transform_climate_variable(self, nc_file, aoi, variable_name):
        """Process ERA5 climate variable and extract hourly statistics."""
        if not nc_file or not os.path.exists(nc_file):
            self.logger.warning(f"{variable_name} file missing")
            return None

        self.logger.info(f"Transforming {variable_name}...")
        
        try:
            ds = xr.open_dataset(nc_file)
            main_var = list(ds.data_vars)[0]
            data = ds[main_var]
            bbox = aoi.to_crs(epsg=4326).total_bounds
            
            # Find dimensions
            lat_dim = lon_dim = time_dim = None
            for dim in data.dims:
                if dim in ['latitude', 'lat', 'y']:
                    lat_dim = dim
                elif dim in ['longitude', 'lon', 'x']:
                    lon_dim = dim
                elif dim in ['time', 'valid_time']:
                    time_dim = dim
            
            if not all([lat_dim, lon_dim, time_dim]):
                self.logger.error(f"Could not identify dimensions")
                ds.close()
                return None
            
            data_subset = data.sel(
                {lon_dim: slice(bbox[0], bbox[2]),
                 lat_dim: slice(bbox[3], bbox[1])}
            )
            
            timesteps = data_subset[time_dim].values
            stats_list = []
            
            for i, time in enumerate(timesteps):
                time_data = data_subset.isel({time_dim: i})
                values = time_data.values
                valid_values = values[~np.isnan(values)]
                
                if len(valid_values) == 0:
                    continue
                
                stats = {
                    'timestamp': pd.Timestamp(time).strftime('%Y-%m-%d %H:%M:%S'),
                    'date': pd.Timestamp(time).strftime('%Y-%m-%d'),
                    f'{variable_name}_mean': float(np.mean(valid_values)),
                    f'{variable_name}_min': float(np.min(valid_values)),
                    f'{variable_name}_max': float(np.max(valid_values)),
                    f'{variable_name}_std': float(np.std(valid_values)),
                }
                stats_list.append(stats)
            
            ds.close()
            self.logger.info(f" {len(stats_list)} timesteps processed")
            return stats_list
            
        except Exception as e:
            self.logger.error(f"Error: {e}")
            return None

    def transform_temperature(self, temp_file, aoi):
        stats = self.transform_climate_variable(temp_file, aoi, 'temperature')
        if stats:
            for s in stats:
                s['temperature_mean'] -= 273.15
                s['temperature_min'] -= 273.15
                s['temperature_max'] -= 273.15
        return stats

    def transform_precipitation(self, precip_file, aoi):
        stats = self.transform_climate_variable(precip_file, aoi, 'precipitation')
        if stats:
            for s in stats:
                s['precipitation_mean'] *= 1000
                s['precipitation_min'] *= 1000
                s['precipitation_max'] *= 1000
        return stats

    def transform_humidity(self, humidity_file, aoi):
        stats = self.transform_climate_variable(humidity_file, aoi, 'humidity')
        if stats:
            for s in stats:
                s['humidity_mean'] -= 273.15
                s['humidity_min'] -= 273.15
                s['humidity_max'] -= 273.15
        return stats

    def transform_soil_moisture(self, soil_file, aoi):
        return self.transform_climate_variable(soil_file, aoi, 'soil_moisture')
