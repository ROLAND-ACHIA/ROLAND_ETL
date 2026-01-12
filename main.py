from .auth.auth import get_cdse_token
from .extract.extract import Extract
from .transform.transform import Transform
from .load.load import Load
from .utils.config import AOI_ZIP_PATH

def run():
    print("="*70)
    print("AGRICONNECT ETL PIPELINE")
    print("="*70)
    
    # Authenticate with CDSE
    cdse_token = get_cdse_token()
    
    # Initialize pipeline components
    extractor = Extract(cdse_token)
    transformer = Transform()
    loader = Load()
    
    # EXTRACT
    print("\n EXTRACTING AOI...")
    aoi, bbox = extractor.get_aoi(AOI_ZIP_PATH)
    
    print("\n EXTRACTING SENTINEL-2 DATA...")
    # Request up to 31 images to cover the entire month (accounting for ~5 day revisit)
    sentinel_products = extractor.get_sentinel2(bbox, max_images=31)
    print(f"   Downloaded {len(sentinel_products)} Sentinel-2 products")
    
    # Get unique dates
    unique_dates = sorted(list(set([p['date'] for p in sentinel_products if p['date']])))
    print(f"   Covering {len(unique_dates)} unique dates: {', '.join(unique_dates)}")
    
    print("\n  EXTRACTING CLIMATE DATA...")
    climate_data = extractor.get_all_climate_data(bbox)
    
    # TRANSFORM
    print("\n TRANSFORMING DATA...")
    
    # Transform Sentinel-2 images (returns dict with date -> indices)
    indices_by_date = transformer.transform_sentinel2(sentinel_products, aoi)
    print(f"   Processed vegetation indices for {len(indices_by_date)} unique dates")
    
    # Transform climate data
    climate_stats = {}
    
    if climate_data.get('temperature'):
        climate_stats['temperature'] = transformer.transform_temperature(
            climate_data['temperature'], aoi
        )
    
    if climate_data.get('precipitation'):
        climate_stats['precipitation'] = transformer.transform_precipitation(
            climate_data['precipitation'], aoi
        )
    
    if climate_data.get('humidity'):
        climate_stats['humidity'] = transformer.transform_humidity(
            climate_data['humidity'], aoi
        )
    
    if climate_data.get('soil_moisture'):
        climate_stats['soil_moisture'] = transformer.transform_soil_moisture(
            climate_data['soil_moisture'], aoi
        )
    
    # LOAD
    print("\n SAVING RESULTS...")
    loader.load_results(indices_by_date, climate_stats)
    
    print("\nETL pipeline completed successfully.")
    print(f" Results saved to: ETL_Results/processed/")
    print(f" Combined CSV ready for ML analysis!")
    print(f"\nData Coverage:")
    print(f"   Sentinel-2 dates: {len(unique_dates)}")
    print(f"   Climate data: Full hourly coverage for December 2024")

if __name__ == "__main__":
    run()
