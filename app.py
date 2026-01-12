from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import os
import threading
from datetime import datetime, timedelta
import zipfile
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PARENT_DIR)

from ROLAND_ETL.auth.auth import get_cdse_token
from ROLAND_ETL.extract.extract import Extract
from ROLAND_ETL.transform.transform import Transform
from ROLAND_ETL.load.load import Load
from ROLAND_ETL.utils.config import ETL_RESULTS_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR

app = Flask(__name__)
app.config['SECRET_KEY'] = 'agriconnect-etl-secret-2024'
app.config['UPLOAD_FOLDER'] = os.path.join(ETL_RESULTS_DIR, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

etl_status = {'running': False, 'progress': 0, 'stage': 'idle', 'current_location': '', 'locations_processed': 0, 'total_locations': 0, 'logs': [], 'output_file': None}

def emit_log(message, level='info'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = {'timestamp': timestamp, 'level': level, 'message': message}
    etl_status['logs'].append(log_entry)
    socketio.emit('log', log_entry)
    print(f"[{timestamp}] {message}")

def emit_progress(progress, stage, location=''):
    etl_status['progress'] = progress
    etl_status['stage'] = stage
    etl_status['current_location'] = location
    socketio.emit('progress', {'progress': progress, 'stage': stage, 'location': location, 'locations_processed': etl_status['locations_processed'], 'total_locations': etl_status['total_locations']})

def extract_shapefile(zip_path, extract_dir):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.shp'):
                    return os.path.join(root, file)
        raise FileNotFoundError("No .shp file found in ZIP archive")
    except Exception as e:
        raise Exception(f"Failed to extract shapefile: {str(e)}")

def process_single_location(location_name, shapefile_path, start_date, end_date):
    try:
        emit_log(f"Processing location: {location_name}", 'info')
        emit_log(f"Date range: {start_date} to {end_date}", 'info')
        emit_log(f"Authenticating with CDSE...", 'info')
        token = get_cdse_token()
        emit_log(f"Extracting data for {location_name}...", 'info')
        
        extractor = Extract(cdse_token=token, start_date=start_date, end_date=end_date)
        aoi, bbox = extractor.get_aoi(shapefile_path)
        products = extractor.get_sentinel2(bbox, max_images=100)
        
        if not products:
            emit_log(f"No Sentinel-2 products found for {location_name}", 'warning')
            return None
        emit_log(f"Downloaded {len(products)} Sentinel-2 products", 'success')
        
        emit_log(f"Extracting climate data for {location_name}...", 'info')
        climate_data = extractor.get_all_climate_data(bbox)
        emit_log(f"Climate data extracted", 'success')
        
        emit_log(f"Transforming data for {location_name}...", 'info')
        transformer = Transform()
        
        indices_by_date = transformer.transform_sentinel2(products, aoi)
        emit_log(f"Calculated vegetation indices for {len(indices_by_date)} dates", 'success')
        
        if indices_by_date:
            sample_dates = list(indices_by_date.keys())[:3]
            emit_log(f"Sample Sentinel-2 dates: {', '.join(sample_dates)}", 'info')
        
        climate_stats = {}
        if climate_data.get('temperature'):
            climate_stats['temperature'] = transformer.transform_temperature(climate_data['temperature'], aoi)
        if climate_data.get('precipitation'):
            climate_stats['precipitation'] = transformer.transform_precipitation(climate_data['precipitation'], aoi)
        if climate_data.get('humidity'):
            climate_stats['humidity'] = transformer.transform_humidity(climate_data['humidity'], aoi)
        if climate_data.get('soil_moisture'):
            climate_stats['soil_moisture'] = transformer.transform_soil_moisture(climate_data['soil_moisture'], aoi)
        
        emit_log(f"Calculated climate statistics", 'success')
        emit_log(f"Creating combined dataset with forward-filled indices for {location_name}...", 'info')
        
        import pandas as pd
        import numpy as np
        
        timestep_records = []
        for var_name, stats_list in climate_stats.items():
            if stats_list:
                for stats in stats_list:
                    ts = stats['timestamp']
                    date = stats['date']
                    existing = None
                    for record in timestep_records:
                        if record['timestamp'] == ts:
                            existing = record
                            break
                    if not existing:
                        timestep_records.append({'timestamp': ts, 'date': date})
        
        if not timestep_records:
            emit_log(f"No climate timesteps found for {location_name}", 'warning')
            return None
        
        sorted_dates = sorted(list(set([r['date'] for r in timestep_records])))
        sorted_indices_dates = sorted(list(indices_by_date.keys()))
        
        emit_log(f"Total days in dataset: {len(sorted_dates)}", 'info')
        emit_log(f"Days with Sentinel-2 images: {len(sorted_indices_dates)}", 'info')
        
        if sorted_dates:
            emit_log(f"Climate date range: {sorted_dates[0]} to {sorted_dates[-1]}", 'info')
        if sorted_indices_dates:
            emit_log(f"Sentinel-2 date range: {sorted_indices_dates[0]} to {sorted_indices_dates[-1]}", 'info')
        
        start_date_obj = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
        end_date_obj = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')
        
        all_dates = []
        current = start_date_obj
        while current <= end_date_obj:
            all_dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        emit_log(f"Generating {len(all_dates)} days from {all_dates[0]} to {all_dates[-1]}", 'info')
        
        date_to_indices = {}
        current_indices = None
        
        for date in all_dates:
            if date in indices_by_date:
                current_indices = indices_by_date[date]
                date_to_indices[date] = current_indices
                emit_log(f"Found indices for {date}: NDVI={current_indices.get('NDVI', 'N/A')}", 'info')
            elif current_indices is not None:
                date_to_indices[date] = current_indices
            else:
                date_to_indices[date] = None
        
        filled_count = sum(1 for d in all_dates if date_to_indices.get(d) is not None)
        emit_log(f"Forward-filled indices across {filled_count}/{len(all_dates)} days", 'success')
        
        all_records = []
        for ts_record in timestep_records:
            ts = ts_record['timestamp']
            date = ts_record['date']
            record = {'timestamp': ts, 'date': date}
            
            for var_name in ['temperature', 'precipitation', 'humidity', 'soil_moisture']:
                record[f'{var_name}_mean'] = np.nan
                record[f'{var_name}_min'] = np.nan
                record[f'{var_name}_max'] = np.nan
                record[f'{var_name}_std'] = np.nan
                
                if var_name in climate_stats and climate_stats[var_name]:
                    for stats in climate_stats[var_name]:
                        if stats['timestamp'] == ts:
                            record[f'{var_name}_mean'] = stats.get(f'{var_name}_mean', np.nan)
                            record[f'{var_name}_min'] = stats.get(f'{var_name}_min', np.nan)
                            record[f'{var_name}_max'] = stats.get(f'{var_name}_max', np.nan)
                            record[f'{var_name}_std'] = stats.get(f'{var_name}_std', np.nan)
                            break
            
            if date in date_to_indices and date_to_indices[date] is not None:
                indices = date_to_indices[date]
                for name, value in indices.items():
                    if value is not None:
                        record[name.upper()] = float(value)
                    else:
                        record[name.upper()] = np.nan
            else:
                for name in ['NDVI', 'EVI', 'SAVI', 'NDMI', 'CHLOROPHYLL', 'LAI', 'CROP_STRESS']:
                    record[name] = np.nan
            
            all_records.append(record)
        
        df = pd.DataFrame(all_records)
        df['location'] = location_name
        
        non_null_indices = df['NDVI'].notna().sum()
        emit_log(f"{location_name} processed: {len(df)} rows, {non_null_indices} with indices data", 'success')
        
        return df
        
    except Exception as e:
        emit_log(f"Error processing {location_name}: {str(e)}", 'error')
        import traceback
        emit_log(f"Traceback: {traceback.format_exc()}", 'error')
        return None

def run_etl_pipeline(zip_files, start_date, end_date):
    global etl_status
    try:
        etl_status['running'] = True
        etl_status['logs'] = []
        etl_status['total_locations'] = len(zip_files)
        etl_status['locations_processed'] = 0
        
        emit_log("=" * 70, 'info')
        emit_log("AGRICONNECT MULTI-LOCATION ETL PIPELINE STARTED", 'info')
        emit_log("=" * 70, 'info')
        emit_log(f"Total locations to process: {len(zip_files)}", 'info')
        emit_log(f"Date range: {start_date} to {end_date}", 'info')
        all_dataframes = []
        for idx, zip_file in enumerate(zip_files):
            location_name = os.path.splitext(os.path.basename(zip_file))[0]
            progress = int((idx / len(zip_files)) * 100)
            emit_progress(progress, 'extracting', location_name)
            emit_log(f"\n{'=' * 70}", 'info')
            emit_log(f"LOCATION {idx + 1}/{len(zip_files)}: {location_name}", 'info')
            emit_log(f"{'=' * 70}", 'info')
            extract_dir = os.path.join(app.config['UPLOAD_FOLDER'], f'extracted_{location_name}')
            os.makedirs(extract_dir, exist_ok=True)
            try:
                shapefile_path = extract_shapefile(zip_file, extract_dir)
                emit_log(f"Shapefile extracted: {os.path.basename(shapefile_path)}", 'success')
            except Exception as e:
                emit_log(f"Failed to extract shapefile: {str(e)}", 'error')
                continue
            emit_progress(progress + 5, 'transforming', location_name)
            df = process_single_location(location_name, shapefile_path, start_date, end_date)
            if df is not None:
                all_dataframes.append(df)
                etl_status['locations_processed'] += 1
            shutil.rmtree(extract_dir, ignore_errors=True)
        if not all_dataframes:
            emit_log("No data was successfully processed", 'error')
            etl_status['running'] = False
            emit_progress(100, 'failed')
            return
        emit_log(f"\n{'=' * 70}", 'info')
        emit_log("COMBINING DATA FROM ALL LOCATIONS", 'info')
        emit_log(f"{'=' * 70}", 'info')
        emit_progress(90, 'loading', 'All locations')
        import pandas as pd
        final_df = pd.concat(all_dataframes, ignore_index=True)
        cols = ['location'] + [col for col in final_df.columns if col != 'location']
        final_df = final_df[cols]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"agriconnect_multi_location_{timestamp}.csv"
        output_path = os.path.join(PROCESSED_DATA_DIR, output_filename)
        final_df.to_csv(output_path, index=False)
        etl_status['output_file'] = output_path
        emit_log(f"Combined CSV saved: {output_filename}", 'success')
        emit_log(f"Total rows: {len(final_df)}", 'info')
        emit_log(f"Total columns: {len(final_df.columns)}", 'info')
        emit_log(f"Locations processed: {etl_status['locations_processed']}/{etl_status['total_locations']}", 'info')
        unique_locations = final_df['location'].unique()
        emit_log(f"Unique locations in dataset: {', '.join(unique_locations)}", 'info')
        
        for col in ['NDVI', 'EVI', 'SAVI', 'NDMI', 'CHLOROPHYLL', 'LAI', 'CROP_STRESS']:
            if col in final_df.columns:
                non_null = final_df[col].notna().sum()
                percentage = (non_null / len(final_df)) * 100
                emit_log(f"{col}: {non_null}/{len(final_df)} rows ({percentage:.1f}%)", 'info')
        
        emit_log("\n" + "=" * 70, 'info')
        emit_log("ETL PIPELINE COMPLETED SUCCESSFULLY", 'success')
        emit_log("=" * 70, 'info')
        emit_progress(100, 'completed', 'All locations')
    except Exception as e:
        emit_log(f"CRITICAL ERROR: {str(e)}", 'error')
        import traceback
        emit_log(f"Traceback: {traceback.format_exc()}", 'error')
        emit_progress(100, 'failed')
    finally:
        etl_status['running'] = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        files = request.files.getlist('files[]')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        if start_date:
            start_date = start_date + "T00:00:00Z"
        else:
            start_date = "2024-12-01T00:00:00Z"
            
        if end_date:
            end_date = end_date + "T23:59:59Z"
        else:
            end_date = "2024-12-31T23:59:59Z"
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        uploaded_files = []
        for file in files:
            if file and file.filename.endswith('.zip'):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                uploaded_files.append(filepath)
        if not uploaded_files:
            return jsonify({'error': 'No valid ZIP files uploaded'}), 400
        thread = threading.Thread(target=run_etl_pipeline, args=(uploaded_files, start_date, end_date))
        thread.daemon = True
        thread.start()
        return jsonify({'success': True, 'message': f'{len(uploaded_files)} files uploaded successfully', 'files': [os.path.basename(f) for f in uploaded_files]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download_result():
    if etl_status['output_file'] and os.path.exists(etl_status['output_file']):
        return send_file(etl_status['output_file'], as_attachment=True, download_name=os.path.basename(etl_status['output_file']))
    return jsonify({'error': 'No output file available'}), 404

@app.route('/status')
def get_status():
    return jsonify(etl_status)

@socketio.on('connect')
def handle_connect():
    emit('status', etl_status)

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("AGRICONNECT ETL DASHBOARD STARTING")
    print("=" * 70)
    print(f"Dashboard URL: http://localhost:5000")
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Results folder: {PROCESSED_DATA_DIR}")
    print("=" * 70 + "\n")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
