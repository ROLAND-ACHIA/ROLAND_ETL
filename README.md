# ROLAND-ETL: ETL Package for Satellite and Climate Data Integration

This package implements a complete **ETL (Extract, Transform, Load)** pipeline for integrating:
- **Sentinel-2 optical imagery** (via Copernicus Data Space Ecosystem)
- **ERA5 reanalysis temperature data** (via WEkEO platform)
- **AOI shapefiles** defining regions of interest


## 📦 Package Structure

etl/
│
├── auth/ → Authentication for CDSE and WEkEO APIs
├── extract/ → Data extraction modules (AOI, Sentinel-2, ERA5)
├── transform/ → Processing of Sentinel-2 indices and temperature
├── load/ → Result export and summary generation
├── utils/ → Configuration, logging, and shared helpers
└── main.py → Main pipeline orchestrator
└── __init__.py
