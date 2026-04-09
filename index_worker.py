import threading
import queue
import time
import os
import psutil
import platform

class UniversalBackgroundIndexer:
    def __init__(self, db, doc_chunker):
        self.db = db
        self.doc_chunker = doc_chunker
        self.task_queue = queue.Queue()
        self.is_running = True
        self.is_paused = False

        # Thresholds
        self.CPU_THRESHOLD = 40.0
        self.RAM_THRESHOLD = 75.0

        self._apply_os_priority()

        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _apply_os_priority(self):
        """Sets priority based on the operating system."""
        p = psutil.Process(os.getpid())
        system = platform.system()

        try:
            if system == "Windows":
                # Only runs when CPU is idle. Perfect for gaming.
                p.nice(psutil.IDLE_PRIORITY_CLASS)
            elif system in ["Linux", "Darwin"]: # Darwin = macOS
                # 'Nice' value of 19 is the lowest priority on Unix.
                p.nice(19)

                # Linux-Specific: Lower the I/O priority too
                # This prevents the indexer from slowing down your SSD/HDD
                if system == "Linux" and hasattr(p, 'ionice'):
                    try:
                        p.ionice(psutil.IOPRIO_CLASS_IDLE)
                    except Exception: pass
        except Exception as e:
            print(f"Priority Note: {e} (Falling back to default)")

    def add_to_queue(self, file_paths):
        for path in file_paths:
            self.task_queue.put(path)

    def _is_system_busy(self):
        """Universal check for CPU and RAM pressure."""
        cpu_usage = psutil.cpu_percent(interval=0.5)
        ram_usage = psutil.virtual_memory().percent

        if cpu_usage > self.CPU_THRESHOLD or ram_usage > self.RAM_THRESHOLD:
            return True, f"CPU: {cpu_usage}%, RAM: {ram_usage}%"
        return False, ""

    def _process_queue(self):
        while self.is_running:
            if not self.task_queue.empty():
                busy, status = self._is_system_busy()

                if busy:
                    self.is_paused = True
                    # If busy, wait 30 seconds before checking again to stay out of the way
                    time.sleep(30)
                    continue

                self.is_paused = False
                filepath = self.task_queue.get()
                self._index_file(filepath)
                self.task_queue.task_done()

                # Breath period between files
                time.sleep(1)
            else:
                # Idle wait when queue is empty
                time.sleep(10)

    def _index_file(self, filepath):
        try:
            filename = os.path.basename(filepath)
            # Use 'errors=ignore' to handle binary files that might sneak in
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if len(content.strip()) < 10:
                return

            chunks = self.doc_chunker.chunk_document(content)
            for i, chunk in enumerate(chunks):
                self.db.insert("user_entries", {
                    "content": chunk,
                    "tags": ["background-indexed"],
                    "filename": filename,
                    "filepath": filepath,
                    "chunk_index": i
                })
        except Exception as e:
            print(f"Background Error indexing {filepath}: {e}")

    def get_status(self):
        return {
            "queue_size": self.task_queue.qsize(),
            "is_paused": self.is_paused
        }