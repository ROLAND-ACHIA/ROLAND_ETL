from .auth.auth import get_cdse_token
from .extract.extract import Extract
from .transform.transform import Transform
from .load.load import Load
from .utils.config import AOI_ZIP_PATH

def run():
    print("="*70)
    print("🚀 AGRICONNECT ETL PIPELINE")
    print("="*70)
    
    # Authenticate with CDSE
    cdse_token = get_cdse_token()
    
    # Initialize pipeline components
    extractor = Extract(cdse_token)
    transformer = Transform()
    loader = Load()
    
    # EXTRACT
    print("\n📍 EXTRACTING AOI...")
    aoi, bbox = extractor.get_aoi(AOI_ZIP_PATH)
    
    print("\n🛰️  EXTRACTING SENTINEL-2 DATA (Multiple Images)...")
    sentinel_products = extractor.get_sentinel2(bbox, max_images=10)
    print(f"   Found {len(sentinel_products)} Sentinel-2 products")
    
    print("\n🌡️  EXTRACTING CLIMATE DATA...")
    climate_data = extractor.get_all_climate_data(bbox)
    
    # TRANSFORM
    print("\n🔄 TRANSFORMING DATA...")
    
    # Transform Sentinel-2 images (returns dict with date -> indices)
    indices_by_date = transformer.transform_sentinel2(sentinel_products, aoi)
    print(f"   Processed vegetation indices for {len(indices_by_date)} dates")
    
    # Transform climate data (returns dict with variable -> list of timestamped stats)
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
    print("\n💾 SAVING RESULTS...")
    loader.load_results(indices_by_date, climate_stats)
    
    print("\n✅ ETL pipeline completed successfully.")
    print(f"📁 Results saved to: ETL_Results/processed/")
    print(f"📊 Combined CSV ready for ML analysis!")

if __name__ == "__main__":
    run()
