import os
import numpy as np
import matplotlib.pyplot as plt
from timing_metrics import get_file_uploads, get_model_responses, TIMING_DATA_DIR

PLOTS_DIR = "./timing_plots"

def _ensure_plots_dir():
    os.makedirs(PLOTS_DIR, exist_ok=True)

def update_file_upload_plot():
    _ensure_plots_dir()
    file_uploads = get_file_uploads()
    
    if not file_uploads:
        return
    
    chunks = [f["chunks"] for f in file_uploads]
    total_times = [f["total_time"] for f in file_uploads]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(chunks, total_times, alpha=0.7, s=50)
    
    if len(chunks) > 1:
        z = np.polyfit(chunks, total_times, 1)
        p = np.poly1d(z)
        x_line = [min(chunks), max(chunks)]
        ax.plot(x_line, [p(x) for x in x_line], "r--", alpha=0.8, label=f"Trend: {z[0]:.4f}s per chunk")
        ax.legend()
    
    ax.set_xlabel("Number of Chunks")
    ax.set_ylabel("Upload Time (seconds)")
    ax.set_title("File Upload Time vs Number of Chunks")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "file_timing.png"))
    plt.close()

def update_model_response_plot():
    _ensure_plots_dir()
    responses = get_model_responses()
    
    if not responses:
        return
    
    retrieval_times = [r["retrieval_time"] for r in responses]
    generation_times = [r["generation_time"] for r in responses]
    total_times = [r["total_time"] for r in responses]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    x = range(1, len(responses) + 1)
    ax1.plot(x, retrieval_times, "b-o", label="Retrieval Time", alpha=0.7)
    ax1.plot(x, generation_times, "g-o", label="Generation Time", alpha=0.7)
    ax1.plot(x, total_times, "r-o", label="Total Time", alpha=0.7)
    ax1.set_xlabel("Query Number")
    ax1.set_ylabel("Time (seconds)")
    ax1.set_title("Model Response Time Breakdown")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    ax2.bar(x, total_times, color="purple", alpha=0.7)
    ax2.set_xlabel("Query Number")
    ax2.set_ylabel("Total Time (seconds)")
    ax2.set_title("Total Model Response Time per Query")
    ax2.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "model_timing.png"))
    plt.close()
