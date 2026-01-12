# AgriConnect ETL Pipeline

An automated ETL pipeline with web-based dashboard for processing satellite imagery and climate data for precision agriculture applications.

## Prerequisites

Before starting, ensure you have:
- Docker installed (recommended) OR Python 3.8+
- Internet connection for downloading satellite and climate data
- Shapefile ZIP files for your areas of interest

---

## Step 1: Get API Credentials

You need to register for two free services to access satellite and climate data.

### A. CDSE Account (for Sentinel-2 satellite data)

1. Go to https://dataspace.copernicus.eu/
2. Click "Register" and create a free account
3. Verify your email address
4. Log in and note your email and password

These credentials will be used as CDSE_USERNAME and CDSE_PASSWORD.

### B. CDS Account (for ERA5 climate data)

1. Go to https://cds.climate.copernicus.eu/user/register
2. Create a free account and verify your email
3. Log in to your account
4. Go to https://cds.climate.copernicus.eu/user to find your API key
5. Your API key format is: UID:API_KEY (example: 12345:abcd-efgh-1234-5678)
6. Accept the ERA5 license terms at https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels

This API key will be used as CDS_API_KEY.

---

## Step 2: Configuration

Now that you have your API credentials, set up the configuration file.

### Edit the environment file with your credentials 


Replace the placeholder values with your actual credentials: 
```
CDSE_USERNAME=your_email@example.com
CDSE_PASSWORD=your_actual_password
CDS_URL=https://cds.climate.copernicus.eu/api
CDS_API_KEY=12345:abcd-efgh-1234-5678
START_DATE=2024-12-01T00:00:00Z
END_DATE=2024-12-31T23:59:59Z
```

**Important notes:**
- CDSE_USERNAME: Use the email you registered with at dataspace.copernicus.eu
- CDSE_PASSWORD: Use your actual password (keep this secure)
- CDS_API_KEY: Copy exactly as shown on your CDS profile page
- START_DATE and END_DATE: Modify to your desired date range/You can still adjust it directly on the dashboard. 
- Date format must be: YYYY-MM-DDTHH:MM:SSZ

 

## Step 3: Installation and Running

### Option 1: Using Docker (Recommended)

Docker ensures all dependencies are correctly installed and isolated.

**Build the Docker image:**
```bash
cd ROLAND_ETL
docker build -t agriconnect-etl .
```
This will take 5-10 minutes to download and install all required packages.

**Run the container:**
```bash
docker run -p 5000:5000 \
           -v $(pwd)/ETL_Results:/app/ETL_Results \
           -v $(pwd)/Shape_files_AOI:/app/ROLAND_ETL/Shape_files_AOI \
           --env-file .env \
           agriconnect-etl
 
### Option 2: Local Installation

If you prefer to run without Docker:

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Start the dashboard:**
```bash
python -m ROLAND_ETL.app
```

The application will start and show you the URL to access.

---

## Step 4: Using the Dashboard

### Access the dashboard

Open your web browser and go to:
```
http://localhost:5000
```

You should see the AgriConnect ETL Dashboard interface.

### Process your data

1. **Set Date Range**: 
   - Select start date (e.g., 2022-01-01)
   - Select end date (e.g., 2022-12-31)
   - Recommendation: Use dates between 2022-2024 for best Sentinel-2 coverage

2. **Upload Shapefiles**: 
   - Click the upload zone or drag and drop
   - Select one or more ZIP files containing shapefiles
   - Each ZIP must contain: .shp, .shx, .dbf, and .prj files
   - Multiple locations can be uploaded at once

3. **Start Pipeline**: 
   - Click "Start ETL Pipeline" button
   - Do not close the browser during processing

4. **Monitor Progress**: 
   - Watch the real-time progress bar
   - View live logs showing each processing stage
   - See statistics for locations processed

5. **Download Results**: 
   - When complete, "Download Combined CSV" button appears
   - Click to download your processed dataset
   - CSV contains all locations with climate and vegetation data


 
 

## Project Structure
```
ROLAND_ETL/
├── auth/              # CDSE authentication
├── extract/           # Download Sentinel-2 and ERA5 data
├── transform/         # Calculate indices and statistics
├── load/              # Export to CSV
├── utils/             # Configuration and logging
├── templates/         # Web dashboard interface
├── app.py            # Flask application
├── .env.dist         # Environment template (do not edit)
├── .env              # Your credentials (you edit this)
└── Dockerfile        # Docker configuration
```

---

## Troubleshooting

### Problem: Port 5000 already in use

**Cause:** Another application is using port 5000.

**Solution:** Kill the process:
```bash
lsof -ti:5000 | xargs kill -9
```

Or use a different port in Docker:
```bash
docker run -p 8080:5000 ...
```
Then access at http://localhost:8080

### Problem: Authentication errors

**Cause:** Incorrect credentials in .env file.

**Solution:**
- Verify your CDSE email and password are correct
- Check CDS API key format (should be UID:KEY)
- Ensure no extra spaces in .env file
- Make sure you accepted the ERA5 license

### Problem: Slow processing

**Cause:** Large date ranges or many locations.

**Expected behavior:**
- Sentinel-2 images: 500MB-1GB each, takes time to download
- ERA5 data: Depends on date range, can take several minutes
- Processing: 1-5 minutes per location after download

**Tips:**
- Process 3-5 locations at a time
- Use smaller date ranges (1-3 months) for faster results

---

## Technical Details

**Data Sources:**
- Sentinel-2: https://dataspace.copernicus.eu/
- ERA5: https://cds.climate.copernicus.eu/

**Technologies:**
- Flask: Web framework
- Socket.IO: Real-time updates
- GeoPandas: Spatial data processing
- Xarray: Climate data handling

**Forward-Fill Algorithm:**
When Sentinel-2 images are not available daily, the system carries forward the most recent indices:
- Day 1: Image available, NDVI=0.75
- Days 2-5: No images, use NDVI=0.75
- Day 6: New image, NDVI=0.82
- Days 7+: Use NDVI=0.82 until next image

This ensures complete time series for analysis.

---

## Support

For issues or questions:
- Email: rolandachia7@gmail.com
- Include error logs from the dashboard

---

## Author

Roland Achia
AIMS Cameroon
rolandachia7@gmail.com

Version 2.0.0 - December 2025

---

## License

This project is developed for academic and research purposes.
