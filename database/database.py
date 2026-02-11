import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from datetime import datetime
from ..utils.config import DATABASE_URL
from ..utils.logging import setup_logger


class Database:
    
    def __init__(self):
        self.logger = setup_logger("database")
        self.database_url = DATABASE_URL
        self.engine = None

    def connect(self):
        try:
            self.engine = create_engine(self.database_url)
            self.logger.info("Database connection established")
            return True
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            return False

    def create_tables_if_not_exist(self):
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id SERIAL PRIMARY KEY,
            farm_id VARCHAR(100) NOT NULL,
            location VARCHAR(255) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            date DATE NOT NULL,
            temperature_mean DOUBLE PRECISION,
            temperature_min DOUBLE PRECISION,
            temperature_max DOUBLE PRECISION,
            temperature_std DOUBLE PRECISION,
            precipitation_mean DOUBLE PRECISION,
            precipitation_min DOUBLE PRECISION,
            precipitation_max DOUBLE PRECISION,
            precipitation_std DOUBLE PRECISION,
            humidity_mean DOUBLE PRECISION,
            humidity_min DOUBLE PRECISION,
            humidity_max DOUBLE PRECISION,
            humidity_std DOUBLE PRECISION,
            soil_moisture_mean DOUBLE PRECISION,
            soil_moisture_min DOUBLE PRECISION,
            soil_moisture_max DOUBLE PRECISION,
            soil_moisture_std DOUBLE PRECISION,
            ndvi DOUBLE PRECISION,
            evi DOUBLE PRECISION,
            savi DOUBLE PRECISION,
            ndmi DOUBLE PRECISION,
            chlorophyll DOUBLE PRECISION,
            lai DOUBLE PRECISION,
            crop_stress DOUBLE PRECISION,
            etl_run_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_reading UNIQUE (farm_id, timestamp)
        );
        CREATE INDEX IF NOT EXISTS idx_sensor_readings_farm_date ON sensor_readings(farm_id, date);
        CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp);
        CREATE INDEX IF NOT EXISTS idx_sensor_readings_location ON sensor_readings(location);
        """
        create_etl_runs_table = """
        CREATE TABLE IF NOT EXISTS etl_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(100) UNIQUE NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            status VARCHAR(50),
            locations_processed INTEGER,
            total_locations INTEGER,
            records_inserted INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_etl_runs_start_time ON etl_runs(start_time);
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.execute(text(create_etl_runs_table))
                conn.commit()
            self.logger.info("Database tables verified/created successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create tables: {e}")
            return False

    def load_dataframe(self, df, etl_run_id):
        try:
            if df.empty or len(df) == 0:
                self.logger.warning("Empty DataFrame provided, nothing to load")
                return 0
            df = df.copy()
            df['etl_run_id'] = etl_run_id
            df['farm_id'] = df['location'].apply(lambda x: f"farm_{x.lower().replace(' ', '_')}")
            column_mapping = {'NDVI': 'ndvi', 'EVI': 'evi', 'SAVI': 'savi', 'NDMI': 'ndmi', 'CHLOROPHYLL': 'chlorophyll', 'LAI': 'lai', 'CROP_STRESS': 'crop_stress'}
            df = df.rename(columns=column_mapping)
            if df['timestamp'].dtype == 'object':
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['date'].dtype == 'object':
                df['date'] = pd.to_datetime(df['date']).dt.date
            df = df.replace([float('inf'), float('-inf')], float('nan'))
            records_inserted = df.to_sql('sensor_readings', self.engine, if_exists='append', index=False, method='multi', chunksize=1000)
            self.logger.info(f"Successfully inserted {len(df)} records into database")
            return len(df)
        except Exception as e:
            self.logger.error(f"Failed to load data into database: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def start_etl_run(self, run_id, total_locations):
        sql = "INSERT INTO etl_runs (run_id, start_time, status, total_locations) VALUES (:run_id, :start_time, :status, :total_locations)"
        try:
            with self.engine.connect() as conn:
                conn.execute(text(sql), {'run_id': run_id, 'start_time': datetime.now(), 'status': 'running', 'total_locations': total_locations})
                conn.commit()
            self.logger.info(f"ETL run {run_id} started")
            return True
        except Exception as e:
            self.logger.error(f"Failed to record ETL run start: {e}")
            return False

    def complete_etl_run(self, run_id, locations_processed, records_inserted, status='completed', error_message=None):
        sql = "UPDATE etl_runs SET end_time = :end_time, status = :status, locations_processed = :locations_processed, records_inserted = :records_inserted, error_message = :error_message WHERE run_id = :run_id"
        try:
            with self.engine.connect() as conn:
                conn.execute(text(sql), {'end_time': datetime.now(), 'status': status, 'locations_processed': locations_processed, 'records_inserted': records_inserted, 'error_message': error_message, 'run_id': run_id})
                conn.commit()
            self.logger.info(f"ETL run {run_id} completed with status: {status}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to record ETL run completion: {e}")
            return False

    def test_connection(self):
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                self.logger.info("Database connection test successful")
                return True
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False

    def close(self):
        if self.engine:
            self.engine.dispose()
            self.logger.info("Database connection closed")
