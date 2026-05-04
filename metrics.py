import time
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
import os

class MetricsTracker:
    def __init__(self):
        self.data = []
        self.start_times = {}

    def start_timer(self, label):
        self.start_times[label] = time.time()

    def stop_timer(self, label, metadata=None):
        if label in self.start_times:
            duration = time.time() - self.start_times[label]
            entry = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "operation": label,
                "duration_sec": round(duration, 4)
            }
            if metadata:
                entry.update(metadata)

            self.data.append(entry)
            print(f"--- [METRIC] {label}: {entry['duration_sec']}s | Info: {metadata or ''} ---")
            return duration

    def generate_research_plots(self):
        if not self.data:
            print("No metrics data to plot.")
            return

        df = pd.DataFrame(self.data)
        os.makedirs("./research_data", exist_ok=True)

        # Plot 1: Operation Duration Comparison
        plt.figure(figsize=(10, 6))
        avg_durations = df.groupby('operation')['duration_sec'].mean().sort_values()
        avg_durations.plot(kind='barh', color='skyblue')
        plt.title('Average Execution Time per Operation')
        plt.xlabel('Seconds')
        plt.tight_layout()
        plt.savefig('./research_data/operation_efficiency.png')

        # Plot 2: Throughput (If indexing chunks)
        if 'chunk_count' in df.columns:
            plt.figure(figsize=(10, 6))
            plt.scatter(df['chunk_count'], df['duration_sec'])
            plt.title('Scaling: File Size vs. Processing Time')
            plt.xlabel('Number of Chunks')
            plt.ylabel('Time (s)')
            plt.savefig('./research_data/scaling_analysis.png')

        print(f"\n[RESEARCH] Plots generated in ./research_data/")