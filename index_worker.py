from datetime import datetime
import threading
import queue
import time
import os
import psutil
from tag_generation import generate_tags_with_llm


class UniversalBackgroundIndexer:
    def __init__(self, db, doc_chunker):
        self.db = db
        self.doc_chunker = doc_chunker
        self.task_queue = queue.Queue()
        self.is_running = True

        # States
        self.manual_pause = False
        self.system_busy = False # True if other apps are using high CPU/RAM

        # Thresholds (Measuring OTHER apps only)
        self.OTHER_CPU_THRESHOLD = 30.0 # If others use >30%, we drop to 10% duty cycle
        self.OTHER_RAM_THRESHOLD = 80.0

        self._apply_os_priority()

        # Start the background worker thread
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _apply_os_priority(self):
        """Sets the OS-level priority to ensure we don't 'steal' cycles from games/apps."""
        p = psutil.Process(os.getpid())
        try:
            if os.name == 'nt':
                p.nice(psutil.IDLE_PRIORITY_CLASS)
            else:
                p.nice(19)
        except Exception as e:
            print(f"Priority Note: {e}")

    def add_to_queue(self, file_paths):
        """The missing method: Takes a list of strings and adds them to the queue."""
        if not file_paths:
            return
        for path in file_paths:
            self.task_queue.put(path)
        print(f"Queue updated. Total files waiting: {self.task_queue.qsize()}")

    def _get_resource_usage(self):
        """Calculates current system pressure excluding this specific Python process."""
        total_cpu = psutil.cpu_percent(interval=0.1)
        process = psutil.Process(os.getpid())

        # Get our app's CPU usage normalized across all cores
        with process.oneshot():
            app_cpu = process.cpu_percent() / psutil.cpu_count()

        other_cpu = max(0, total_cpu - app_cpu)
        ram_usage = psutil.virtual_memory().percent

        return other_cpu, ram_usage

    def _process_queue(self):
        while self.is_running:
            # Handle Manual Pause
            if self.manual_pause:
                time.sleep(1)
                continue

            if not self.task_queue.empty():
                other_cpu, ram_usage = self._get_resource_usage()

                # Dynamic Throttling Logic (10% vs 60%)
                if other_cpu > self.OTHER_CPU_THRESHOLD or ram_usage > self.OTHER_RAM_THRESHOLD:
                    target_duty_cycle = 0.10 # Limit to 10% of time
                    self.system_busy = True
                else:
                    target_duty_cycle = 0.60 # Limit to 60% of time (staying snappy)
                    self.system_busy = False

                filepath = self.task_queue.get()

                # Measure how long the actual work takes
                start_work = time.time()
                self._index_file(filepath)
                work_duration = time.time() - start_work

                # Duty Cycle Math: (Work / TotalTime) = Target
                # This forces the thread to sleep proportional to how hard it just worked
                sleep_duration = (work_duration / target_duty_cycle) - work_duration

                # Ensure we don't sleep forever, but respect the throttle
                time.sleep(max(0.1, sleep_duration))

                self.task_queue.task_done()
            else:
                # No files to process? Nap for a bit.
                time.sleep(5)

    def _index_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if not content.strip(): return

            # 1. Generate Context Embedding for the whole file
            file_context = content[:1000] # Use the start of the file for context
            context_vector = self.db.embedder.embed_text(file_context)

            # 2. Search for existing tags (> 0.8)
            assigned_tags = self.db.get_semantic_tags(context_vector, threshold=0.8)

            # 3. If no tags found, generate new ones
            if not assigned_tags:
                print(f"No matching tags for {os.path.basename(filepath)}. Generating...")
                new_tags = generate_tags_with_llm(file_context)
                for nt in new_tags:
                    self.db.add_new_tag(nt)
                    assigned_tags.append(nt)

            # 4. Chunk and Index
            chunks = self.doc_chunker.chunk_document(content)
            for i, chunk in enumerate(chunks):
                if self.manual_pause: break

                # OPTIONAL: Add chunk-specific tagging if it's long enough
                chunk_tags = list(assigned_tags)
                if len(chunk.split()) > 50:
                    # Semantic search for chunk-specific tags from existing pool
                    cv = self.db.embedder.embed_text(chunk)
                    specific = self.db.get_semantic_tags(cv, threshold=0.85)
                    chunk_tags = list(set(chunk_tags + specific))

                self.db.insert("user_entries", {
                    "content": chunk,
                    "tags": chunk_tags,
                    "filename": os.path.basename(filepath),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            print(f"Tagging/Indexing Error: {e}")

    def get_status(self):
        """Used by the Flask API to update the UI status bar."""
        return {
            "queue_size": self.task_queue.qsize(),
            "manual_pause": self.manual_pause,
            "throttled": self.system_busy
        }