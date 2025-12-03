# ROLAND ETL Pipeline 🌾

**Smart Agriculture Data Processing Pipeline**

Automatically downloads and processes satellite imagery and climate data for agriculture analysis.

---

## �� What You Get

- **Sentinel-2 satellite images** → Vegetation health indicators (NDVI, EVI, etc.)
- **ERA5 climate data** → Temperature, rainfall, humidity, soil moisture
- **Output**: Ready-to-use CSV file for machine learning

---

## 🚀 Quick Start (3 Steps)

### Step 1: Get Your API Keys

#### A. Copernicus Data Space (for satellite images)
1. Register: https://dataspace.copernicus.eu/
2. Save your email and password

#### B. Climate Data Store (for weather data)
1. Register: https://cds.climate.copernicus.eu/user/register
2. Login and go to: https://cds.climate.copernicus.eu/user
3. Copy your API key (looks like: `12345:abcd-efgh-1234-5678`)
4. Accept the license: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
   (Click "Download data" tab → Accept terms)

### Step 2: Setup Your Computer

Create a file called `.cdsapirc` in your home directory:

**Linux/Mac:**
```bash
cat > ~/.cdsapirc << 'EOL'
url: https://cds.climate.copernicus.eu/api
key: YOUR_UID:YOUR_API_KEY
EOL
```

**Windows:** Create `C:\Users\YourName\.cdsapirc` with:
```
url: https://cds.climate.copernicus.eu/api
key: YOUR_UID:YOUR_API_KEY
```

### Step 3: Run the Pipeline
```bash
# 1. Build the container (one time only)
docker build -t roland-etl .

# 2. Run the pipeline
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape_files_AOI:/app/ROLAND_ETL/Shape_files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    -e CDSE_USERNAME="your_email@example.com" \
    -e CDSE_PASSWORD="your_password" \
    roland-etl

# Results will be in: ETL_Results/processed/agriconnect_data_*.csv
```

---

## 📁 What You Need

### Required Files

1. **Your shapefile** (area of interest) → Put in `Shape_files_AOI/` folder as a ZIP file
2. **API credentials** (from Step 1)

### Folder Structure
```
ROLAND_ETL/
├── Shape_files_AOI/
│   └── your_area.zip          ← Your shapefile here
├── ETL_Results/                ← Results appear here
│   ├── raw/                    (downloaded data)
│   └── processed/              (final CSV file)
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## ⚙️ Configuration

### Change Date Range

Edit `utils/config.py` before building:
```python
START_DATE = "2024-12-01T00:00:00Z"
END_DATE = "2024-12-31T23:59:59Z"
```

Or use environment variables when running:
```bash
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape_files_AOI:/app/ROLAND_ETL/Shape_files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    -e CDSE_USERNAME="your_email@example.com" \
    -e CDSE_PASSWORD="your_password" \
    -e START_DATE="2024-01-01T00:00:00Z" \
    -e END_DATE="2024-01-31T23:59:59Z" \
    roland-etl
```

### Change Your Area (Shapefile)

1. Replace the ZIP file in `Shape_files_AOI/` folder
2. Update the path in `utils/config.py`:
```python
AOI_ZIP_PATH = os.path.join(BASE_DIR, "Shape_files_AOI/YOUR_FILE.zip")
```
3. Rebuild: `docker build -t roland-etl .`

---

## 📊 Output Data

You'll get a CSV file with these columns:

| What | Description |
|------|-------------|
| `timestamp` | Date and time (hourly) |
| `temperature_mean` | Temperature (°C) |
| `precipitation_mean` | Rainfall (mm) |
| `humidity_mean` | Humidity (°C dewpoint) |
| `soil_moisture_mean` | Soil water content |
| `NDVI` | Vegetation health (0-1) |
| `EVI` | Enhanced vegetation index |
| `CROP_STRESS` | Stress level (0=healthy, 1=stressed) |

**Location**: `ETL_Results/processed/agriconnect_data_YYYYMMDD_HHMMSS.csv`

---

## ❓ Troubleshooting

### "Error 401: Unauthorized" (Satellite download)
- Check your CDSE email and password are correct
- Make sure you're registered at https://dataspace.copernicus.eu/

### "CDS API error" (Climate download)
- Check your `.cdsapirc` file exists in your home directory
- Verify your API key is correct
- Did you accept the ERA5 license?

### "No shapefile found"
- Make sure your ZIP file is in `Shape_files_AOI/` folder
- Check the filename matches in `utils/config.py`

### Pipeline takes too long
- Normal! Downloading satellite images takes 5-10 minutes each
- A full month (10 images) can take 1-2 hours

---

## 🎯 Example Run
```bash
# Complete example
cd /home/student/Documents/NMD\ project/ROLAND_ETL

# Build
docker build -t roland-etl .

# Run for December 2024
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape_files_AOI:/app/ROLAND_ETL/Shape_files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    -e CDSE_USERNAME="rolandachia7@gmail.com" \
    -e CDSE_PASSWORD="YourPassword123" \
    roland-etl

# Check results
ls -lh ETL_Results/processed/
```

---

## 📧 Support

**Author**: Roland Achia  
**Email**: rolandachia7@gmail.com  
**Organization**: AIMS Cameroon

For issues, email me with:
- Your error message
- The command you ran
- Your operating system

---

**Version**: 1.0.0  
**Last Updated**: December 2024
