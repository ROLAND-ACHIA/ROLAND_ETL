import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Automatically set BASE_DIR to the ROLAND_ETL root directory
BASE_DIR = str(Path(__file__).resolve().parent.parent)

# Define ETL Results directory - will be mounted from host
ETL_RESULTS_DIR = os.path.expanduser("~/Documents/NMD project/ETL_Results")
RAW_DATA_DIR = os.path.join(ETL_RESULTS_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(ETL_RESULTS_DIR, "processed")

# Create directories if they don't exist (in case not mounted)
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

# AOI shapefile path (inside ROLAND_ETL package)
AOI_ZIP_PATH = os.path.join(BASE_DIR, "Shape files_AOI/Abong-Mbang_WH.zip")

# CDSE API Credentials (for Sentinel-2)
CDSE_USERNAME = os.getenv("CDSE_USERNAME", "rolandachia7@gmail.com")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD", "AChia672083022@")

# CDS API Credentials (for ERA5 climate data)
CDS_URL = os.getenv("CDS_URL", "https://cds.climate.copernicus.eu/api")
CDS_API_KEY = os.getenv("CDS_API_KEY", "70fc350f-0222-4fcb-ac82-1b9389025a21")

# Date range for data extraction - Full December 2024
START_DATE = os.getenv("START_DATE", "2024-12-01T00:00:00Z")
END_DATE = os.getenv("END_DATE", "2024-12-31T23:59:59Z")

# ERA5 variables to download
ERA5_VARIABLES = {
    'temperature': '2m_temperature',
    'precipitation': 'total_precipitation',
    'humidity': '2m_dewpoint_temperature',
    'soil_moisture': 'volumetric_soil_water_layer_1'
}

# Database Configuration (Supabase PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "db.vbhkvbtijkecqshejnll.supabase.co")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "iloveshalomchow")

# Build database connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
