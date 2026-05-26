import json
import os
from datetime import datetime
from typing import Optional

TIMING_DATA_DIR = "./timingData"
TIMING_DATA_FILE = os.path.join(TIMING_DATA_DIR, "timing_data.json")

def _ensure_dir():
    os.makedirs(TIMING_DATA_DIR, exist_ok=True)

def _load_data() -> dict:
    _ensure_dir()
    if os.path.exists(TIMING_DATA_FILE):
        try:
            with open(TIMING_DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"file_uploads": [], "folder_uploads": [], "model_responses": []}

def _save_data(data: dict):
    _ensure_dir()
    with open(TIMING_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def record_file_upload(filename: str, chunks: int, upload_time: float, embed_time: float, db_time: float, total_time: float):
    data = _load_data()
    data["file_uploads"].append({
        "filename": filename,
        "chunks": chunks,
        "upload_time": round(upload_time, 4),
        "embed_time": round(embed_time, 4),
        "db_time": round(db_time, 4),
        "total_time": round(total_time, 4),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    })
    _save_data(data)

def record_folder_upload(folder_name: str, file_count: int, total_chunks: int, total_time: float):
    data = _load_data()
    data["folder_uploads"].append({
        "folder_name": folder_name,
        "file_count": file_count,
        "total_chunks": total_chunks,
        "total_time": round(total_time, 4),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    })
    _save_data(data)

def record_model_response(query_preview: str, retrieval_time: float, generation_time: float, total_time: float):
    data = _load_data()
    data["model_responses"].append({
        "query_preview": query_preview[:50] if query_preview else "",
        "retrieval_time": round(retrieval_time, 4),
        "generation_time": round(generation_time, 4),
        "total_time": round(total_time, 4),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    })
    _save_data(data)

def get_file_uploads() -> list:
    return _load_data().get("file_uploads", [])

def get_folder_uploads() -> list:
    return _load_data().get("folder_uploads", [])

def get_model_responses() -> list:
    return _load_data().get("model_responses", [])
