 FROM python:3.11-slim

LABEL maintainer="Roland Achia <rolandachia7@gmail.com>"
LABEL description="AgriConnect ETL Dashboard - Multi-Location Precision Agriculture Data Pipeline"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

COPY requirements.txt .

# Install with increased timeout and retries
RUN pip install --default-timeout=300 --retries 5 --no-cache-dir -r requirements.txt

COPY . /app/ROLAND_ETL

RUN mkdir -p /app/ETL_Results/raw /app/ETL_Results/processed /app/ETL_Results/uploads

ENV PYTHONPATH=/app
ENV ETL_RESULTS_DIR=/app/ETL_Results

EXPOSE 5000

WORKDIR /app

CMD ["python", "-m", "ROLAND_ETL.app"]
