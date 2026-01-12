import os
import zipfile
import requests
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import xarray as xr
import numpy as np
import csv
from datetime import datetime
import time

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = "/home/student/Documents/NMD project"
RAW_DATA_DIR = os.path.join(BASE_DIR, "data/raw")
PROCESSED_DATA_DIR = os.path.join(BASE_DIR, "data/processed")
AOI_ZIP_PATH = os.path.join(BASE_DIR, "Shape files_AOI/Abong-Mbang_WH.zip")

os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

# --- CDSE Credentials ---
CDSE_USERNAME = "rolandachia7@gmail.com"
CDSE_PASSWORD = "AChia672083022@"

# --- WEkEO Credentials ---
WEKEO_USERNAME = "achia10"
WEKEO_PASSWORD = "AChia672083022@"

# Date range for data collection
START_DATE = "2024-01-01T00:00:00Z"
END_DATE = "2024-12-31T23:59:59Z"

# ============================================================
# AUTHENTICATION
# ============================================================

def get_cdse_token():
    """Get access token from Copernicus Data Space."""
    print(" Authenticating with CDSE...")
    url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "username": CDSE_USERNAME,
        "password": CDSE_PASSWORD,
        "client_id": "cdse-public"
    }
    try:
        r = requests.post(url, data=data, timeout=60)
        r.raise_for_status()
        token = r.json()["access_token"]
        print("CDSE authentication successful")
        return token
    except Exception as e:
        print(f" CDSE authentication failed: {e}")
        return None

def get_wekeo_token():
    """Get access token from WEkEO."""
    print(" Authenticating with WEkEO...")
    url = "https://gateway.prod.wekeo2.eu/hda-broker/gettoken"
    data = {"username": WEKEO_USERNAME, "password": WEKEO_PASSWORD}
    try:
        r = requests.post(url, json=data, timeout=60)
        r.raise_for_status()
        token = r.json()["access_token"]
        print(" WEkEO authentication successful")
        return token
    except Exception as e:
        print(f" WEkEO authentication failed: {e}")
        return None

# ============================================================
# EXTRACT - AOI
# ============================================================

def extract_aoi(zip_path):
    """Extract and load AOI shapefile."""
    print("\n EXTRACT: Loading AOI shapefile...")

    # Find or extract shapefile
    shp_files = []
    for root, dirs, files in os.walk(RAW_DATA_DIR):
        shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])

    if not shp_files:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(RAW_DATA_DIR)
        for root, dirs, files in os.walk(RAW_DATA_DIR):
            shp_files.extend([os.path.join(root, f) for f in files if f.endswith(".shp")])

    if not shp_files:
        raise FileNotFoundError("No .shp file found!")

    aoi = gpd.read_file(shp_files[0])
    bbox = aoi.to_crs(epsg=4326).total_bounds
    print(f" AOI loaded: {os.path.basename(shp_files[0])}")
    print(f"   Bounding box: {bbox}")
    return aoi, bbox

# ============================================================
# EXTRACT - SENTINEL-2 (CDSE)
# ============================================================

def extract_sentinel2(token, bbox):
    """Search and download Sentinel-2 data from CDSE."""
    print("\n EXTRACT: Sentinel-2 from CDSE...")

    url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    filter_query = (
        f"Collection/Name eq 'SENTINEL-2' and "
        f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and "
        f"att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},"
        f"{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))') and "
        f"ContentDate/Start gt {START_DATE} and ContentDate/Start lt {END_DATE}"
    )

    params = {"$filter": filter_query, "$orderby": "ContentDate/Start asc", "$top": 1}

    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        products = r.json().get("value", [])

        if not products:
            print(" No Sentinel-2 products found")
            return None

        product = products[0]
        product_id = product["Id"]
        product_name = product["Name"]
        print(f" Found: {product_name}")

        # Download
        download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
        headers = {"Authorization": f"Bearer {token}"}

        zip_path = os.path.join(RAW_DATA_DIR, f"{product_name}.zip")

        # Check if already downloaded
        if os.path.exists(zip_path):
            print(f" Product already downloaded")
        else:
            print(f" Downloading...")
            with requests.get(download_url, headers=headers, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            print(f" Download complete")

        # Extract
        extract_folder = os.path.join(RAW_DATA_DIR, product_name)
        if not os.path.exists(extract_folder):
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_folder)
            print(f" Extracted to: {extract_folder}")

        return extract_folder

    except Exception as e:
        print(f" Sentinel-2 extraction failed: {e}")
        return None

# ============================================================
# EXTRACT - TEMPERATURE (WEkEO)
# ============================================================

def extract_temperature(token, bbox):
    """Download ERA5 temperature data from WEkEO."""
    print("\n🌡️ EXTRACT: Temperature data from WEkEO...")

    north, south = round(bbox[3], 2), round(bbox[1], 2)
    east, west = round(bbox[2], 2), round(bbox[0], 2)

    # Submit job
    url = "https://gateway.prod.wekeo2.eu/hda-broker/api/v1/dataaccess/jobs"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    job_data = {
        "datasetId": "EO:ECMWF:DAT:REANALYSIS_ERA5_SINGLE_LEVELS",
        "stringChoiceValues": [
            {"name": "product_type", "value": ["reanalysis"]},
            {"name": "variable", "value": ["2m_temperature"]},
            {"name": "year", "value": ["2024"]},
            {"name": "month", "value": ["january", "february"]},
            {"name": "day", "value": ["01", "15"]},
            {"name": "time", "value": ["12:00"]},
            {"name": "data_format", "value": ["netcdf"]},
        ],
        "boundingBoxValues": [{"name": "area", "bbox": [north, west, south, east]}]
    }

    try:
        r = requests.post(url, headers=headers, json=job_data, timeout=60)
        r.raise_for_status()
        job_id = r.json().get("jobId")

        if not job_id:
            print(" Failed to submit job")
            return None

        print(f" Job submitted: {job_id}")
        print(" Monitoring job (max 10 minutes)...")

        # Monitor job
        status_url = f"https://gateway.prod.wekeo2.eu/hda-broker/api/v1/dataaccess/jobs/{job_id}"
        start_time = time.time()
        max_wait = 600  # 10 minutes

        while (time.time() - start_time) < max_wait:
            r = requests.get(status_url, headers=headers, timeout=60)
            status = r.json().get("status", "unknown")

            if status == "completed":
                print(" Job completed!")
                break
            elif status == "failed":
                print(f" Job failed")
                return None

            time.sleep(20)
        else:
            print("⏰ Job timeout - continuing with available data")
            return None

        # Download result
        result_url = f"https://gateway.prod.wekeo2.eu/hda-broker/api/v1/dataaccess/jobs/{job_id}/result"
        r = requests.get(result_url, headers=headers, timeout=60)
        download_url = r.json().get("url")

        if not download_url:
            print(" No download URL available")
            return None

        # Download file
        nc_path = os.path.join(RAW_DATA_DIR, "ERA5_temperature_2024.nc")
        r = requests.get(download_url, stream=True, timeout=300)
        with open(nc_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        print(f"Temperature data downloaded: {nc_path}")
        return nc_path

    except Exception as e:
        print(f"Temperature extraction failed: {e}")
        return None

# ============================================================
# TRANSFORM - SENTINEL-2 INDICES
# ============================================================

def transform_sentinel2(product_folder, aoi):
    """Compute vegetation and soil indices from Sentinel-2."""
    print("\n🔄 TRANSFORM: Computing Sentinel-2 indices...")

    # Find band files
    band_map = {}
    for root, dirs, files in os.walk(product_folder):
        for f in files:
            fname = f.upper()
            if fname.endswith("B02.JP2"): band_map["B2"] = os.path.join(root, f)
            if fname.endswith("B04.JP2"): band_map["B4"] = os.path.join(root, f)
            if fname.endswith("B05.JP2"): band_map["B5"] = os.path.join(root, f)
            if fname.endswith("B08.JP2"): band_map["B8"] = os.path.join(root, f)
            if fname.endswith("B11.JP2"): band_map["B11"] = os.path.join(root, f)

    required = ["B2", "B4", "B5", "B8", "B11"]
    if not all(b in band_map for b in required):
        print(f" Missing bands")
        return None

    # Use B4 (10m resolution) as reference
    with rasterio.open(band_map["B4"]) as ref:
        ref_meta = ref.meta.copy()
        aoi_proj = aoi.to_crs(ref.crs)
        ref_arr, ref_transform = mask(ref, aoi_proj.geometry, crop=True)
        ref_shape = ref_arr[0].shape

        out_meta = ref_meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": ref_shape[0],
            "width": ref_shape[1],
            "transform": ref_transform,
            "count": 1,
            "dtype": rasterio.float32
        })

    # Read and clip bands, resampling to reference shape
    bands = {}
    from rasterio.warp import reproject, Resampling

    for key, path in band_map.items():
        with rasterio.open(path) as src:
            # Clip to AOI
            arr, transform = mask(src, aoi_proj.geometry, crop=True)

            # If shape doesn't match reference, resample
            if arr[0].shape != ref_shape:
                print(f"   Resampling {key} from {arr[0].shape} to {ref_shape}")
                resampled = np.empty(ref_shape, dtype=np.float32)
                reproject(
                    source=arr[0],
                    destination=resampled,
                    src_transform=transform,
                    src_crs=src.crs,
                    dst_transform=ref_transform,
                    dst_crs=ref.crs,
                    resampling=Resampling.bilinear
                )
                bands[key] = resampled.astype(float)
            else:
                bands[key] = arr[0].astype(float)

    # Compute indices
    indices = {
        "NDVI": (bands["B8"] - bands["B4"]) / (bands["B8"] + bands["B4"] + 1e-6),
        "EVI": 2.5 * (bands["B8"] - bands["B4"]) / (bands["B8"] + 6*bands["B4"] - 7.5*bands["B2"] + 1),
        "CHLORO": (bands["B5"] / (bands["B4"] + 1e-6)) - 1,
        "SOILM": (bands["B11"] - bands["B8"]) / (bands["B11"] + bands["B8"] + 1e-6)
    }

    # Save indices as GeoTIFFs
    for name, arr in indices.items():
        out_path = os.path.join(PROCESSED_DATA_DIR, f"{name.lower()}_index.tif")
        with rasterio.open(out_path, "w", **out_meta) as dst:
            dst.write(arr.astype(rasterio.float32), 1)
        print(f" Saved {name} → {out_path}")

    return indices

# ============================================================
# TRANSFORM - TEMPERATURE DATA
# ============================================================

def transform_temperature(nc_path, aoi):
    """Process temperature data and compute statistics."""
    print("\n TRANSFORM: Processing temperature data...")

    try:
        ds = xr.open_dataset(nc_path)

        # Get temperature variable (usually t2m)
        temp_var = None
        for var in ['t2m', '2t', 'temperature_2m']:
            if var in ds.variables:
                temp_var = var
                break

        if not temp_var:
            print(f"Temperature variable not found. Available: {list(ds.variables)}")
            return None

        # Extract data
        temp_data = ds[temp_var]

        # Convert from Kelvin to Celsius if needed
        if temp_data.max() > 200:  # Likely in Kelvin
            temp_data = temp_data - 273.15

        # Compute statistics
        stats = {
            "mean_temp": float(temp_data.mean()),
            "min_temp": float(temp_data.min()),
            "max_temp": float(temp_data.max()),
            "std_temp": float(temp_data.std())
        }

        print(f" Temperature stats computed:")
        print(f"   Mean: {stats['mean_temp']:.2f}°C")
        print(f"   Min: {stats['min_temp']:.2f}°C")
        print(f"   Max: {stats['max_temp']:.2f}°C")

        ds.close()
        return stats

    except Exception as e:
        print(f"Temperature processing failed: {e}")
        return None

# ============================================================
# LOAD - SAVE RESULTS
# ============================================================

def load_results(sentinel_indices, temp_stats):
    """Save all results to CSV summary file."""
    print("\nLOAD: Saving results...")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_path = os.path.join(PROCESSED_DATA_DIR, f"etl_summary_{timestamp}.csv")

    with open(summary_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["metric", "value", "unit"])

        # Sentinel-2 indices
        if sentinel_indices:
            writer.writerow(["--- SENTINEL-2 INDICES ---", "", ""])
            for name, arr in sentinel_indices.items():
                writer.writerow([f"{name}_mean", f"{np.nanmean(arr):.4f}", "index"])
                writer.writerow([f"{name}_std", f"{np.nanstd(arr):.4f}", "index"])

        # Temperature stats
        if temp_stats:
            writer.writerow(["--- TEMPERATURE STATS ---", "", ""])
            for key, val in temp_stats.items():
                writer.writerow([key, f"{val:.2f}", "°C"])

    print(f"Summary saved: {summary_path}")
    print(f"\n All processed files in: {PROCESSED_DATA_DIR}")

# ============================================================
# MAIN ETL PIPELINE
# ============================================================

def main_etl():
    """Execute complete ETL pipeline."""
    print("="*70)
    print(" INTEGRATED ETL PIPELINE: CDSE + WEkEO")
    print("="*70)

    # Authenticate
    cdse_token = get_cdse_token()
    wekeo_token = get_wekeo_token()

    if not cdse_token:
        print(" CDSE authentication failed - cannot continue")
        return

    # EXTRACT
    print("\n" + "="*70)
    print(" EXTRACT PHASE")
    print("="*70)

    aoi, bbox = extract_aoi(AOI_ZIP_PATH)
    sentinel_folder = extract_sentinel2(cdse_token, bbox)

    temp_file = None
    if wekeo_token:
        temp_file = extract_temperature(wekeo_token, bbox)
    else:
        print(" Skipping temperature data (WEkEO auth failed)")

    # TRANSFORM
    print("\n" + "="*70)
    print(" TRANSFORM PHASE")
    print("="*70)

    sentinel_indices = None
    if sentinel_folder:
        sentinel_indices = transform_sentinel2(sentinel_folder, aoi)

    temp_stats = None
    if temp_file:
        temp_stats = transform_temperature(temp_file, aoi)

    # LOAD
    print("\n" + "="*70)
    print(" LOAD PHASE")
    print("="*70)

    load_results(sentinel_indices, temp_stats)

    # Summary
    print("\n" + "="*70)
    print(" ETL PIPELINE COMPLETED!")
    print("="*70)
    print(f"✓ Sentinel-2 indices: {'SUCCESS' if sentinel_indices else 'FAILED'}")
    print(f"✓ Temperature data: {'SUCCESS' if temp_stats else 'SKIPPED/FAILED'}")
    print("="*70)

if __name__ == "__main__":
    main_etl()
