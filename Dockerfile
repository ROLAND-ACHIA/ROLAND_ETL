FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

ENV CDSE_USERNAME="your_username" \
    CDSE_PASSWORD="YourStrongPassword" \
    CDS_URL="https://cds.climate.copernicus.eu/api"\
    CDS_API_KEY="YourCDSAPIKEY"\
    START_DATE="2024-12-01T00:00:00Z"\
    END_DATE="2024-12-31T23:59:59Z"

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ETL code
COPY . /app/ROLAND_ETL/

# DON'T create directories here - let volumes handle it
# This was the problem: RUN mkdir -p /app/ETL_Results/raw /app/ETL_Results/processed

# Run ETL
CMD ["python", "-m", "ROLAND_ETL.main"]
