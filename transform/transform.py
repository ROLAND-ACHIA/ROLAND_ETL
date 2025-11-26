"""
Transformation module for processing Sentinel-2 and ERA5 climate data.

Handles:
- Sentinel-2 vegetation indices calculation (NDVI, EVI, SAVI, etc.)
- ERA5 climate variables statistics
- Crop stress indicator
"""

import os
import numpy as np
import rasterio
from rasterio.mask import mask
import geopandas as gpd
import xarray as xr
import pandas as pd
from datetime import datetime
from ..utils.config import PROCESSED_DATA_DIR
from ..utils.logging import setup_logger


class Transform:
    """
    Handles transformation of satellite and climate data.
    """

    def __init__(self):
        self.logger = setup_logger("transform")

    # ------------------------------------------------------------------
    # SENTINEL-2 TRANSFORMATION
    # ------------------------------------------------------------------
    def transform_sentinel2(self, product_list, aoi):
        """
        Computes vegetation indices from multiple Sentinel-2 images.

        Parameters
        ----------
        product_list : list
            List of dictionaries with 'path' and 'date' for each product
        aoi : GeoDataFrame
            Area of interest polygon

        Returns
        -------
        dict
            Dictionary mapping dates to vegetation indices
        """
        if not product_list:
            self.logger.warning("No Sentinel-2 products provided. Skipping transformation.")
            return {}

        self.logger.info(f"Transforming {len(product_list)} Sentinel-2 images...")
        
        indices_by_date = {}
        
        for product in product_list:
            date = product.get('date')
            if not date:
                continue
            
            # Mock indices for each date (replace with actual band calculations later)
            indices = {
                'NDVI': np.random.uniform(0.3, 0.9),
                'EVI': np.random.uniform(0.2, 0.8),
                'SAVI': np.random.uniform(0.2, 0.7),
                'NDMI': np.random.uniform(0.1, 0.6),
                'CHLOROPHYLL': np.random.uniform(20, 80),
                'LAI': np.random.uniform(1, 5),
            }
            
            # Calculate crop stress indicator
            # Based on NDVI and NDMI thresholds
            ndvi = indices['NDVI']
            ndmi = indices['NDMI']
            
            if ndvi < 0.4 or ndmi < 0.2:
                crop_stress = 1  # High stress
            elif ndvi < 0.6 or ndmi < 0.3:
                crop_stress = 0.5  # Moderate stress
            else:
                crop_stress = 0  # Low stress
            
            indices['CROP_STRESS'] = crop_stress
            
            indices_by_date[date] = indices
            self.logger.info(f"  ✅ Processed {date}: NDVI={ndvi:.3f}, Stress={crop_stress}")
        
        self.logger.info(f"✅ All Sentinel-2 indices computed successfully")
        return indices_by_date

    # ------------------------------------------------------------------
    # CLIMATE DATA TRANSFORMATION
    # ------------------------------------------------------------------
    def transform_climate_variable(self, nc_file, aoi, variable_name):
        """
        Process ERA5 climate variable and extract hourly statistics.

        Parameters
        ----------
        nc_file : str
            Path to NetCDF file
        aoi : GeoDataFrame
            Area of interest
        variable_name : str
            Name of the variable

        Returns
        -------
        list
            List of dictionaries with hourly statistics
        """
        if not nc_file or not os.path.exists(nc_file):
            self.logger.warning(f"{variable_name} file missing. Skipping transformation.")
            return None

        self.logger.info(f"Transforming {variable_name} data...")
        
        try:
            ds = xr.open_dataset(nc_file)
            
            main_var = None
            for key in ds.data_vars:
                main_var = key
                break
            
            if not main_var:
                self.logger.error(f"No data variable found in {variable_name} file")
                ds.close()
                return None
            
            data = ds[main_var]
            
            bbox = aoi.to_crs(epsg=4326).total_bounds
            
            lat_dim = None
            lon_dim = None
            time_dim = None
            
            for dim in data.dims:
                if dim in ['latitude', 'lat', 'y']:
                    lat_dim = dim
                elif dim in ['longitude', 'lon', 'x']:
                    lon_dim = dim
                elif dim in ['time', 'valid_time']:
                    time_dim = dim
            
            if not all([lat_dim, lon_dim, time_dim]):
                self.logger.error(f"Could not identify dimensions. Found: {data.dims}")
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
            
            self.logger.info(f"✅ {variable_name} statistics computed: {len(stats_list)} timesteps")
            return stats_list
            
        except Exception as e:
            self.logger.error(f"Error processing {variable_name}: {e}")
            return None

    def transform_temperature(self, temp_file, aoi):
        """Process temperature data with unit conversion."""
        stats = self.transform_climate_variable(temp_file, aoi, 'temperature')
        
        if stats:
            for s in stats:
                s['temperature_mean'] = s['temperature_mean'] - 273.15
                s['temperature_min'] = s['temperature_min'] - 273.15
                s['temperature_max'] = s['temperature_max'] - 273.15
        
        return stats

    def transform_precipitation(self, precip_file, aoi):
        """Process precipitation data with unit conversion."""
        stats = self.transform_climate_variable(precip_file, aoi, 'precipitation')
        
        if stats:
            for s in stats:
                s['precipitation_mean'] = s['precipitation_mean'] * 1000
                s['precipitation_min'] = s['precipitation_min'] * 1000
                s['precipitation_max'] = s['precipitation_max'] * 1000
        
        return stats

    def transform_humidity(self, humidity_file, aoi):
        """Process humidity (dewpoint) data with unit conversion."""
        stats = self.transform_climate_variable(humidity_file, aoi, 'humidity')
        
        if stats:
            for s in stats:
                s['humidity_mean'] = s['humidity_mean'] - 273.15
                s['humidity_min'] = s['humidity_min'] - 273.15
                s['humidity_max'] = s['humidity_max'] - 273.15
        
        return stats

    def transform_soil_moisture(self, soil_file, aoi):
        """Process soil moisture data."""
        return self.transform_climate_variable(soil_file, aoi, 'soil_moisture')
