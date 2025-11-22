# ===================================================================
#  Dockerfile for ETL Pipeline from Jupyter Notebook
# ===================================================================
FROM python:3.12-slim

# ===================================================================
#  Install system dependencies for geospatial libraries
# ===================================================================
RUN apt-get update && apt-get install -y \
    build-essential \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# ===================================================================
#  Set GDAL environment variables
# ===================================================================
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# ===================================================================
#  Set working directory
# ===================================================================
WORKDIR /app

# ===================================================================
#  Install Python packages
# ===================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir jupyter nbconvert

# ===================================================================
#  Copy notebook and shape files
# ===================================================================
COPY ROLAND-ETL.ipynb .
COPY "Shape_files_AOI" ./Shape_files_AOI

# ===================================================================
#  Create data directories inside container
# ===================================================================
RUN mkdir -p /app/data/raw /app/data/processed

# ===================================================================
#  Convert notebook to Python script and run it
# ===================================================================
CMD ["bash", "-c", "jupyter nbconvert --to python ROLAND-ETL.ipynb --output etl_script && python etl_script.py"]
