"""
Loading module for saving processed data.

Handles:
- Saving vegetation indices by date
- Saving climate statistics
- Creating combined CSV for ML analysis with date-matched indices
"""

import os
import csv
import numpy as np
import pandas as pd
from datetime import datetime
from ..utils.config import PROCESSED_DATA_DIR
from ..utils.logging import setup_logger


class Load:
    """
    Handles loading/saving of processed data.
    """

    def __init__(self):
        self.logger = setup_logger("load")

    def load_results(self, indices_by_date: dict, climate_stats: dict):
        """
        Save all ETL results including combined CSV for ML.

        Parameters
        ----------
        indices_by_date : dict
            Dictionary mapping dates to vegetation indices
        climate_stats : dict
            Dictionary of climate variable statistics (time series)
        """
        self.logger.info("Saving all ETL results...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save individual numpy arrays for each date's indices
        for date, indices in indices_by_date.items():
            for name, value in indices.items():
                if value is not None and name != 'CROP_STRESS':
                    filepath = os.path.join(PROCESSED_DATA_DIR, f"{name.lower()}_{date}_{timestamp}.npy")
                    np.save(filepath, value)
                    self.logger.info(f"Saved {name} ({date}) -> {filepath}")
        
        # Create combined CSV for ML
        self._create_combined_csv(indices_by_date, climate_stats, timestamp)
        
        self.logger.info(" All ETL results saved successfully.")

    def _create_combined_csv(self, indices_by_date: dict, climate_stats: dict, timestamp: str):
        """
        Create a combined CSV file with hourly climate data matched to daily vegetation indices.

        Parameters
        ----------
        indices_by_date : dict
            Vegetation indices by date
        climate_stats : dict
            Climate statistics (time series)
        timestamp : str
            Timestamp for filename
        """
        self.logger.info("Creating combined CSV for ML analysis...")
        
        # Collect all timesteps from climate data with their dates
        timestep_records = []
        
        for var_name, stats_list in climate_stats.items():
            if stats_list:
                for stats in stats_list:
                    ts = stats['timestamp']
                    date = stats['date']
                    
                    # Find if we already have this timestep
                    existing = None
                    for record in timestep_records:
                        if record['timestamp'] == ts:
                            existing = record
                            break
                    
                    if not existing:
                        timestep_records.append({'timestamp': ts, 'date': date})
        
        if not timestep_records:
            self.logger.warning("No climate data timesteps found.")
            timestep_records = [{'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                               'date': datetime.now().strftime('%Y-%m-%d')}]
        
        self.logger.info(f"Creating {len(timestep_records)} hourly records...")
        
        # Create complete records
        all_records = []
        
        for ts_record in timestep_records:
            ts = ts_record['timestamp']
            date = ts_record['date']
            
            record = {
                'timestamp': ts,
                'date': date
            }
            
            # Add climate variables for this timestep
            for var_name in ['temperature', 'precipitation', 'humidity', 'soil_moisture']:
                record[f'{var_name}_mean'] = np.nan
                record[f'{var_name}_min'] = np.nan
                record[f'{var_name}_max'] = np.nan
                record[f'{var_name}_std'] = np.nan
                
                if var_name in climate_stats and climate_stats[var_name]:
                    for stats in climate_stats[var_name]:
                        if stats['timestamp'] == ts:
                            record[f'{var_name}_mean'] = stats.get(f'{var_name}_mean', np.nan)
                            record[f'{var_name}_min'] = stats.get(f'{var_name}_min', np.nan)
                            record[f'{var_name}_max'] = stats.get(f'{var_name}_max', np.nan)
                            record[f'{var_name}_std'] = stats.get(f'{var_name}_std', np.nan)
                            break
            
            # Add vegetation indices matching the date
            if date in indices_by_date:
                indices = indices_by_date[date]
                for name, value in indices.items():
                    if value is not None:
                        record[name.upper()] = float(value)
                    else:
                        record[name.upper()] = np.nan
            else:
                # No Sentinel-2 data for this date - use NaN or nearest date
                # For simplicity, use NaN
                for name in ['NDVI', 'EVI', 'SAVI', 'NDMI', 'CHLOROPHYLL', 'LAI', 'CROP_STRESS']:
                    record[name] = np.nan
            
            all_records.append(record)
        
        # Convert to DataFrame
        df = pd.DataFrame(all_records)
        
        # Define column order
        columns_order = ['timestamp', 'date']
        
        # Climate variables
        for var in ['temperature', 'precipitation', 'humidity', 'soil_moisture']:
            columns_order.extend([
                f'{var}_mean',
                f'{var}_min',
                f'{var}_max',
                f'{var}_std'
            ])
        
        # Vegetation indices
        for name in ['NDVI', 'EVI', 'SAVI', 'NDMI', 'CHLOROPHYLL', 'LAI', 'CROP_STRESS']:
            columns_order.append(name)
        
        # Reorder columns (only include columns that exist)
        existing_columns = [col for col in columns_order if col in df.columns]
        df = df[existing_columns]
        
        # Save to CSV
        csv_path = os.path.join(PROCESSED_DATA_DIR, f"combined_data_{timestamp}.csv")
        df.to_csv(csv_path, index=False)
        
        self.logger.info(f" Combined CSV saved -> {csv_path}")
        self.logger.info(f"   Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        
        # Print summary statistics
        self.logger.info(f"\n Data Summary:")
        self.logger.info(f"   Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        self.logger.info(f"   Date range: {df['date'].min()} to {df['date'].max()}")
        self.logger.info(f"   Total records: {len(df)}")
        self.logger.info(f"   Unique dates with Sentinel-2 data: {len([d for d in df['date'].unique() if d in indices_by_date])}")
        
        # Print first few rows
        self.logger.info(f"\n   Preview (first 10 rows):")
        print("\n" + df.head(10).to_string())
        
        # Print non-null counts for key columns
        self.logger.info(f"\n   Data availability:")
        key_cols = ['temperature_mean', 'precipitation_mean', 'NDVI', 'CROP_STRESS']
        for col in key_cols:
            if col in df.columns:
                non_null = df[col].notna().sum()
                self.logger.info(f"   {col}: {non_null}/{len(df)} records ({100*non_null/len(df):.1f}%)")
        
        # Save a summary of dates with Sentinel-2 data
        dates_with_s2 = sorted([d for d in indices_by_date.keys()])
        summary_path = os.path.join(PROCESSED_DATA_DIR, f"sentinel2_dates_{timestamp}.txt")
        with open(summary_path, 'w') as f:
            f.write("Dates with Sentinel-2 imagery:\n")
            f.write("="*50 + "\n")
            for date in dates_with_s2:
                indices = indices_by_date[date]
                f.write(f"{date}: NDVI={indices.get('NDVI', 'N/A'):.3f}, ")
                f.write(f"Crop Stress={indices.get('CROP_STRESS', 'N/A'):.2f}\n")
        
        self.logger.info(f" Sentinel-2 dates summary saved -> {summary_path}")
