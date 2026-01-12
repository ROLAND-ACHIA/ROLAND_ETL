# ROLAND ETL Pipeline

**Smart Agriculture Data Processing Pipeline**

Automatically downloads and processes satellite imagery and climate data for agriculture analysis.

---

## �� What You Get

- **Sentinel-2 satellite images**  Vegetation health indicators (NDVI, EVI, LAI, etc.)
- **ERA5 climate data**  Temperature, rainfall, humidity, soil moisture
- **Output**: Ready-to-use CSV file for machine learning and analysis

---

## Quick Start Guide

### Step 1: Get Your API Credentials

You need TWO sets of credentials:

#### A. Copernicus Data Space Ecosystem (CDSE) - For Satellite Images
1. Go to: https://dataspace.copernicus.eu/
2. Click "Register" → Create account
3. **Save your email and password** - you'll need these!

#### B. Climate Data Store (CDS) - For Weather Data
1. Go to: https://cds.climate.copernicus.eu/user/register
2. Create account and login
3. Go to your profile: https://cds.climate.copernicus.eu/user
4. **Copy your API key** - it looks like: `12345:abcd-1234-5678-efgh`
5. **Accept the license**:
   - Go to: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
   - Click "Download data" tab
   - Check the box to accept terms

---

### Step 2: Configure Your Credentials

#### Option A: Edit the Configuration File (Recommended)

Open `utils/config.py` and update these lines:
```python
# CDSE API Credentials (for Sentinel-2)
CDSE_USERNAME = os.getenv("CDSE_USERNAME", "YOUR_EMAIL_HERE")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD", "YOUR_PASSWORD_HERE")
```

**Example:**
```python
CDSE_USERNAME = os.getenv("CDSE_USERNAME", "john.doe@example.com")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD", "MySecurePass123")
```

#### Option B: Use Environment Variables (When Running Docker)

Keep the config file as is, and provide credentials when running:
```bash
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape files_AOI:/app/ROLAND_ETL/Shape files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    -e CDSE_USERNAME="your_email@example.com" \
    -e CDSE_PASSWORD="your_password" \
    roland-etl
```

---

### Step 3: Setup CDS API Key

Create a file called `.cdsapirc` in your home directory with your CDS API key:

**Linux/Mac:**
```bash
cat > ~/.cdsapirc << 'EOL'
url: https://cds.climate.copernicus.eu/api
key: YOUR_UID:YOUR_API_KEY
EOL
```

**Windows:**
Create a file: `C:\Users\YourName\.cdsapirc`

Content:
```
url: https://cds.climate.copernicus.eu/api
key: YOUR_UID:YOUR_API_KEY
```


**Example:**
```
url: https://cds.climate.copernicus.eu/api
key: 12345:abcd-efgh-1234-5678-ijkl-mnop
```

---

### Step 4: Configure Your Area and Date Range

Open `utils/config.py` and modify these settings:

**Change the dates** to your desired time period.

#### Set Date Range
```python
# Date range for data extraction
START_DATE = os.getenv("START_DATE", "2024-12-01T00:00:00Z")
END_DATE = os.getenv("END_DATE", "2024-12-31T23:59:59Z")
```

#### Set Your Shapefile (Area of Interest)
```python
# AOI shapefile path (inside ROLAND_ETL package)
AOI_ZIP_PATH = os.path.join(BASE_DIR, "Shape files_AOI/Abong-Mbang_WH.zip")
```

**Replace `Abong-Mbang_WH.zip`** with your shapefile name.

**Steps:**
1. Put your shapefile ZIP in the `Shape files_AOI/` folder
2. Update the filename in config.py


### Step 5: Prepare Your Files

Make sure you have:
```
ROLAND_ETL/
├── Shape files_AOI/
│   └── YOUR_SHAPEFILE.zip     ← Your area shapefile here
├── ETL_Results/                ← Create this folder (empty)
│   ├── raw/
│   └── processed/
├── app/
│   ├── auth/
│   ├── utils/
│   ├── load/
│   ├── extract/
│   ├── transform/
│   ├── __init__.py
│   └── main.py
└── Dockerfile
```

Create the ETL_Results folder:
```bash
mkdir -p ETL_Results/raw
mkdir -p ETL_Results/processed
```

---

### Step 6: Build and Run

#### Build the Docker Container (one time only)
```bash
cd /path/to/ROLAND_ETL
docker build -t roland-etl .
```

#### Run the Pipeline
```bash
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape files_AOI:/app/ROLAND_ETL/Shape files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    roland-etl
```

**Note:** If you didn't edit `config.py` in Step 2, add your credentials here:
```bash
docker run --rm \
    -v "$(pwd)/ETL_Results:/app/ETL_Results" \
    -v "$(pwd)/Shape files_AOI:/app/ROLAND_ETL/Shape files_AOI" \
    -v "$HOME/.cdsapirc:/root/.cdsapirc:ro" \
    -e CDSE_USERNAME="your_email@example.com" \
    -e CDSE_PASSWORD="your_password" \
    roland-etl
```

---

##  Understanding the Output

### What the Pipeline Does

1. **Downloads Satellite Images** (5-10 minutes per image)
   - Sentinel-2 has ~5-day revisit time
   - For 1 month, you'll get 6-8 images
   - Images saved in: `ETL_Results/raw/`

2. **Downloads Climate Data** (10-20 minutes)
   - Hourly temperature, rainfall, humidity, soil moisture
   - Covers your entire date range
   - Data saved in: `ETL_Results/raw/era5_*.nc`

3. **Processes Data** (1-2 minutes)
   - Calculates vegetation indices
   - Computes climate statistics
   - Matches data by date

4. **Creates CSV File**
   - Location: `ETL_Results/processed/agriconnect_data_TIMESTAMP.csv`
   - Ready for Excel, Python, R, or ML tools



















