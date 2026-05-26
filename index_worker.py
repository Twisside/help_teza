from datetime import datetime
import collections
import subprocess
import threading
import time
import os
import psutil
import json

from document_parser import UniversalParser
from tag_generation import generate_tags_with_llm
from timing_metrics import record_folder_upload, record_file_upload
from plotting import update_file_upload_plot


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

SETTINGS_FILE = "./settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"stay_loaded": True, "target_model": None}

settings = load_settings()

class UniversalBackgroundIndexer:
    def __init__(self, db, doc_chunker, stay_loaded=False):
        self.db = db
        self.doc_chunker = doc_chunker
        self.task_queue = collections.deque()
        self.queue_lock = threading.Lock()
        self.is_running = True
        self.stay_loaded = stay_loaded
        self.batch_start_time = None
        self.total_files = 0
        self.batch_files = 0
        self.batch_chunks = 0

        self.doc_parser = UniversalParser(doc_chunker)

        self.manual_pause = False
        self.system_busy = False

        self.OTHER_CPU_THRESHOLD = 30.0
        self.OTHER_RAM_THRESHOLD = 80.0

        self.queue_complete = True
        self.completion_time = 0
        self.files_completed = 0
        self.has_been_indexed = False
        self.processing_file = None

        self._apply_os_priority()

        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _apply_os_priority(self):
        p = psutil.Process(os.getpid())
        try:
            if os.name == 'nt':
                p.nice(psutil.IDLE_PRIORITY_CLASS)
            else:
                p.nice(19)
        except Exception as e:
            print(f"Priority Note: {e}")

    def add_to_queue(self, file_paths):
        if not file_paths:
            return
        with self.queue_lock:
            for path in file_paths:
                self.task_queue.append(path)
        self.total_files += len(file_paths)
        self.batch_files += len(file_paths)
        if self.batch_start_time is None:
            self.batch_start_time = time.time()
        self.queue_complete = False
        self.has_been_indexed = True
        self.files_completed = 0
        self.batch_chunks = 0
        with self.queue_lock:
            queue_len = len(self.task_queue)
        print(f"Queue updated. Added {len(file_paths)} files. Total: {queue_len}")

    def _get_resource_usage(self):
        total_cpu = psutil.cpu_percent(interval=0.1)
        process = psutil.Process(os.getpid())

        with process.oneshot():
            cpu_count = psutil.cpu_count() or 1
            app_cpu = process.cpu_percent() / cpu_count

        other_cpu = max(0, total_cpu - app_cpu)
        ram_usage = psutil.virtual_memory().percent

        return other_cpu, ram_usage

    def _unload_embedding_model(self):
        if self.stay_loaded:
            return
        embedding_model = "text-embedding-embeddinggemma-300m"
        print(f"Unloading embedding model: {embedding_model}...")
        subprocess.run(["lms", "unload", embedding_model], check=False)

    def _load_embedding_model(self):
        if self.stay_loaded:
            return
        embedding_model = "text-embedding-embeddinggemma-300m"
        print(f"Loading embedding model: {embedding_model}...")
        subprocess.run(["lms", "load", embedding_model], check=True)
        print(f"Embedding model loaded.")

    def _process_queue(self):
        while self.is_running:
            if self.manual_pause:
                time.sleep(1)
                continue

            filepath = None
            with self.queue_lock:
                if not self.task_queue:
                    if self.batch_start_time is not None and self.total_files > 0:
                        self.queue_complete = True
                        self.processing_file = None
                        total_time = time.time() - self.batch_start_time
                        mins = int(total_time // 60)
                        secs = int(total_time % 60)
                        self.completion_time = total_time
                        self.files_completed = self.total_files
                        self.batch_files = 0
                        self.total_files = 0
                        self.batch_start_time = None
                        if not self.stay_loaded:
                            self._unload_embedding_model()
                        print(f">>>Queue fully processed! {self.files_completed} files indexed in {mins}m {secs}s")
                        try:
                            record_folder_upload("batch", self.files_completed, self.batch_chunks, total_time)
                            update_file_upload_plot()
                        except Exception as e:
                            print(f"Warning: Metrics recording failed: {e}")
                    time.sleep(0.1)
                    continue

                filepath = self.task_queue.popleft()

            if filepath is None:
                time.sleep(0.1)
                continue

            self.processing_file = os.path.basename(filepath)

            print(f"[{_ts()}] WORKER: Dequeued file: {os.path.basename(filepath)}")

            other_cpu, ram_usage = self._get_resource_usage()

            if other_cpu > self.OTHER_CPU_THRESHOLD or ram_usage > self.OTHER_RAM_THRESHOLD:
                target_duty_cycle = 0.10
                self.system_busy = True
            else:
                target_duty_cycle = 1.0
                self.system_busy = False

            start_work = time.time()
            print(f"[{_ts()}] WORKER: Starting index for {os.path.basename(filepath)}")
            file_chunks = self._index_file(filepath)
            work_duration = time.time() - start_work
            filename = os.path.basename(filepath)
            if file_chunks:
                self.batch_chunks += file_chunks
            with self.queue_lock:
                remaining = len(self.task_queue)
            print(f">>>Indexed {filename} in {work_duration:.2f}s ({remaining} left)")

            if file_chunks:
                record_file_upload(filename, file_chunks, 0, work_duration, 0, work_duration)
                update_file_upload_plot()

            if file_chunks:
                self.batch_files -= 1

            if not self.stay_loaded:
                print(f"[{_ts()}] WORKER: Unloading embedding model...")
                self._unload_embedding_model()
                time.sleep(0.5)
                print(f"[{_ts()}] WORKER: Loading embedding model...")
                self._load_embedding_model()
                print(f"[{_ts()}] WORKER: Embedding model ready.")

            sleep_duration = (work_duration / target_duty_cycle) - work_duration
            time.sleep(max(0.1, sleep_duration))

    def _index_file(self, filepath):
        filename = os.path.basename(filepath)
        print(f"[{_ts()}] INDEX: Beginning file indexing: {filename}")
        try:
            chunks = self.doc_parser.process_file(filepath)
            if not chunks:
                return 0

            file_context = chunks[0][:1000]
            print(f"[{_ts()}] INDEX: Calling embed_text for context (file: {filename})")
            context_vector = self.db.embedder.embed_text(file_context)
            assigned_tags = self.db.get_semantic_tags(context_vector, threshold=0.8)

            if not assigned_tags:
                print(f"[{_ts()}] INDEX: No matching tags for {filename}. Generating new tags...")
                new_tags = generate_tags_with_llm(file_context, self.stay_loaded)
                if new_tags == ["auto-categorized"]:
                    assigned_tags = new_tags
                else:
                    for nt in new_tags:
                        self.db.add_new_tag(nt)
                    assigned_tags.extend(new_tags)

            chunks_inserted = 0
            for i, chunk in enumerate(chunks):
                if self.manual_pause:
                    break
                self.db.insert("user_entries", {
                    "content": chunk,
                    "tags": assigned_tags,
                    "filename": filename,
                    "chunk_index": i
                })
                chunks_inserted += 1
            print(f"[{_ts()}] INDEX: Completed indexing {filename}")
            return chunks_inserted
        except Exception as e:
            print(f"Indexing Error for {filename}: {e}")
            return 0

    def get_status(self):
        with self.queue_lock:
            qsize = len(self.task_queue)
        return {
            "queue_size": qsize,
            "manual_pause": self.manual_pause,
            "throttled": self.system_busy,
            "queue_complete": self.queue_complete,
            "files_indexed": self.files_completed,
            "batch_files": self.batch_files,
            "completion_time": self.completion_time,
            "has_been_indexed": self.has_been_indexed,
            "processing_file": self.processing_file
        }