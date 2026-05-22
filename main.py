import atexit
import json
import os
import subprocess
import time
from datetime import datetime
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chunker import DocumentChunker
from database import QdrantRepo
from document_parser import UniversalParser
from file_manager import FileManager
from index_worker import UniversalBackgroundIndexer
from tag_generation import generate_tags_with_llm
from chat_handle import ChatSession
from preprocessor import TimeAwarePreprocessor

app = Flask(__name__)

# --- Settings Persistence ---
SETTINGS_FILE = "./settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"stay_loaded": True, "target_model": None}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

settings = load_settings()
STAY_LOADED = settings.get("stay_loaded", False)

# --- Setup Local File System Storage ----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---=-
# will change it so search nad select through the file system
ALLOWED_EXTENSIONS = {'.txt', '.md', '.pdf', '.py', '.js', '.cs'}
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
TARGET_MODEL = "google/gemma-3-1b"
EMBEDDING_MODEL ="text-embedding-embeddinggemma-300m@q4_0" #< ====================================================================
# -=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---


db = QdrantRepo(use_qwen=False) #8187
db.connect()

preprocessor = TimeAwarePreprocessor()
chat_session = ChatSession(db, preprocessor=preprocessor)

doc_chunker = DocumentChunker()
doc_parser = UniversalParser(doc_chunker)


@app.route('/', methods=['GET', 'POST'])
def home():
    error_msg = request.args.get('error')

    if request.method == 'POST':
        entry = request.form.get('user_input')
        raw_tags = request.form.get('tags', '')
        tags_list = [t.strip() for t in raw_tags.split(',') if t.strip()]
        if not tags_list:
            tags_list = ['untagged']

        if entry:
            start_time = time.time()
            text_chunks = doc_chunker.chunk_document(entry)
            for i, chunk in enumerate(text_chunks):
                db.insert("user_entries", {
                    "content": chunk,
                    "tags": tags_list,
                    "filename": "Manual Entry",
                    "chunk_index": i
                })
            process_time = time.time() - start_time

            return jsonify({"status": "success", "message": f"Manual text embedded in {process_time:.2f}s"})

        # This line MUST stay indented inside the POST block!
        return jsonify({"error": "No text provided"}), 400

    # --- GET ROUTING (This is what loads the actual HTML web page) ---
    query = request.args.get('search')
    search_tags_raw = request.args.get('search_tags', '')
    search_tags_list = [t.strip() for t in search_tags_raw.split(',') if t.strip()]

    if query:
        search_results = db.search("user_entries", query, search_tags=search_tags_list if search_tags_list else None,
                                   limit=5)
        all_entries = [{"id": r['id'], **r['payload'], "score": r['score']} for r in search_results]
    else:
        all_entries = db.get_all("user_entries")

    return render_template('home.html', entries=all_entries, is_search=bool(query), error=error_msg)

def process_and_index_file(filepath, filename, tags_list=None):
    def _ts():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{_ts()}] MANUAL: Starting processing {filename}")
    text_chunks = doc_parser.process_file(filepath)
    for i, chunk in enumerate(text_chunks):
        db.insert("user_entries", {
            "content": chunk,
            "tags": tags_list if tags_list else ['untagged'],
            "filename": filename,
            "chunk_index": i
        })
    print(f"[{_ts()}] MANUAL: Completed processing {filename}")
    return len(text_chunks)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file detected."}), 400

    file = request.files['file']

    raw_tags = request.form.get('tags', '')
    tags_list = [t.strip() for t in raw_tags.split(',') if t.strip()]

    if not tags_list:
        try:
            file.seek(0)
            content_preview = file.read().decode('utf-8', errors='ignore')[:1000]
            file.seek(0)

            print("No tags provided. Generating automatic tags...")
            tags_list = generate_tags_with_llm(content_preview)
        except Exception as e:
            print(f"Failed to auto-generate tags: {e}")
            tags_list = ['untagged']

    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400

    if file:
        filename = secure_filename(file.filename)
        _, ext = os.path.splitext(filename)

        if ext.lower() not in ALLOWED_EXTENSIONS:
            print(f"Blocked upload: Unsupported file type '{ext}'")
            return jsonify({"error": f"Unsupported file: {ext}. Allowed: PDF, TXT, MD, PY, JS, CS"}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            start_time = time.time()
            print(f"Processing {filename} with UniversalParser...")

            chunks_count = process_and_index_file(filepath, filename, tags_list)

            process_time = time.time() - start_time
            print(f">>>Upload and embedding complete in {process_time:.2f} seconds")
            return jsonify({"status": "success", "message": f"{filename} ({chunks_count} chunks) embedded in {process_time:.2f}s!"})

        except Exception as e:
            print(f"Error processing or embedding file {filename}: {e}")
            return jsonify({"error": "Server error processing file."}), 500

@app.route('/db/update/<collection>/<item_id>', methods=['POST'])
def updateitem(collection, item_id):
    new_text = request.form.get('updated_content')
    if new_text:
        db.update(collection, item_id, {"content": new_text})

    # Send user back to the home page list
    return jsonify({"status": "success"})


@app.route('/db/delete/<collection>/<item_id>')
def deleteitem(collection, item_id):
    db.delete(collection, item_id)
    return jsonify({"status": "success"})


@app.route('/db/read/<collection>')
def readdb(collection):
    entries = db.get_all(collection)

    return entries


# ----------== File Manage ==--------------



# Initialize the manager
file_mgr = FileManager()

@app.route('/api/get_directory_tree')
def get_directory_tree():
    # Simply call the manager
    tree_data = file_mgr.get_directory_json()
    return jsonify(tree_data)


@app.route('/api/save_selected_dirs', methods=['POST'])
def save_dirs():
    selected_paths = request.json.get('paths', [])
    success = file_mgr.save_selected_config(selected_paths)
    return jsonify({"status": "success" if success else "error"})


# Initialize the worker
bg_indexer = UniversalBackgroundIndexer(db, doc_chunker, STAY_LOADED)

@app.route('/api/indexer_status')
def indexer_status():
    status = bg_indexer.get_status()
    # It's important to return it as JSON
    return jsonify(status)


@app.route('/api/index_directories', methods=['POST'])
def index_directories():
    selected_paths = request.json.get('paths', [])

    # Ensure this method exists in your file_manager.py!
    files = file_mgr.get_all_files_from_paths(selected_paths)

    bg_indexer.add_to_queue(files)

    # Add the "message" key here so JS can find it
    return jsonify({
        "status": "success",
        "count": len(files),
        "message": f"Added {len(files)} files to the background indexing queue."
    })


@app.route('/api/toggle_pause', methods=['POST'])
def toggle_pause():
    bg_indexer.manual_pause = not bg_indexer.manual_pause
    return jsonify({"paused": bg_indexer.manual_pause})
# -------------------------------------

# LM Studio CLI Integration

# Feature flag for your future model.
# Once you download a model (e.g., 'lms get qwen3-coder'), put its name here.

#  TODO:
#   Will make a select menu of models in the future



def start_lm_studio():
    print("Starting LM Studio API server in the background...")
    try:
        subprocess.Popen(["lms", "server", "start"])
        time.sleep(3)

        if EMBEDDING_MODEL:
            print(f"Loading Embedding Model: {EMBEDDING_MODEL}...")
            subprocess.run(["lms", "load", EMBEDDING_MODEL], check=True)
            print(f"{EMBEDDING_MODEL} loaded!")

        if STAY_LOADED and TARGET_MODEL:
            print(f"Loading {TARGET_MODEL} (stay_loaded mode)...")
            subprocess.run(["lms", "load", TARGET_MODEL], check=True)
            print(f"{TARGET_MODEL} locked and loaded!")
        elif TARGET_MODEL:
            print(f"Target model {TARGET_MODEL} loaded on-demand (stay_loaded is False)...")

    except FileNotFoundError:
        print("\nERROR: 'lms' command not found.")
        print("Please install LM Studio and run 'lms bootstrap' in your terminal.\n")
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Failed to load model {TARGET_MODEL}. Is it downloaded?\nDetails: {e}\n")


@app.route('/ask', methods=['POST'])
def ask_ai():
    user_query = request.form.get('question')
    if not user_query:
        return jsonify({"error": "No query provided"}), 400

    if not STAY_LOADED and TARGET_MODEL:
        print(f"Loading {TARGET_MODEL} on-demand...")
        subprocess.run(["lms", "load", TARGET_MODEL], check=False)
        time.sleep(2)

# 1. RETRIEVE
    query_had_time_trigger = preprocessor.should_preprocess(user_query)
    search_query = preprocessor.preprocess_query(user_query) if query_had_time_trigger else user_query

    search_results = db.search("user_entries", search_query, limit=5)
    high_quality = [res for res in search_results if res['score'] > 0.5]
    new_results = high_quality if len(high_quality) >= 3 else search_results[:3]

    # 2. AUGMENT
    context_items = []
    for res in new_results:
        content = res['payload']['content']
        date = res['payload'].get('timestamp', 'Unknown Date')
        source = res['payload'].get('filename', 'Manual Entry')

        if query_had_time_trigger:
            content = preprocessor.preprocess_chunk(content, date)

        formatted_chunk = f"[Recorded on: {date}] [Source: {source}]\nContent: {content}"
        context_items.append(formatted_chunk)

    context_string = "\n\n---\n\n".join(context_items)
    now = datetime.now()

    # 3. GENERATE
    system_prompt = (
        f"You are a helpful assistant. The current date and time is {now}. Answer the user's question based ONLY on the provided context. "
        "Pay attention to the dates provided in the context; if there is conflicting information, "
        "prioritize the most recent entry unless asked otherwise."
        "Use the current date as an anchor to resolve relative time references "
        "like 'yesterday', 'last week', or 'today' when looking at context timestamps."
    )
    user_prompt = f"Context:\n{context_string}\n\nQuestion: {user_query}"

    lm_studio_url = "http://127.0.0.1:1234/v1/chat/completions"
    payload = {
        "model": TARGET_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(lm_studio_url, json=payload)

        if response.status_code != 200:
            ai_answer = f"LM Studio rejected the request. Details: {response.text}"
        else:
            ai_answer = response.json()['choices'][0]['message']['content']

    except requests.exceptions.RequestException as e:
        ai_answer = f"Network Error connecting to LM Studio: {e}"

    #Package the context data cleanly to send to the frontend via JSON
    context_data = [
        {
            "score": round(res['score'], 2),
            "timestamp": res['payload'].get('timestamp', ''),
            "content": res['payload']['content'][:150]
        } for res in new_results
    ]

    #Return pure JSON instead of rendering the HTML template
    return jsonify({
        "ai_answer": ai_answer,
        "retrieved_context": context_data
    })

@app.route('/api/chat/ask', methods=['POST'])
def chat_ask():
    user_query = request.form.get('message')
    if not user_query:
        return jsonify({"error": "No message provided"}), 400

    if not STAY_LOADED and TARGET_MODEL:
        print(f"Loading {TARGET_MODEL} on-demand...")
        subprocess.run(["lms", "load", TARGET_MODEL], check=False)
        time.sleep(2)

    chat_session.add_message("user", user_query)

    context_results = chat_session.search_context(user_query)

    system_prompt = chat_session.build_system_prompt(user_query, context_results)
    conversation_history = chat_session.build_conversation_history()

    lm_studio_url = "http://127.0.0.1:1234/v1/chat/completions"
    messages = [{"role": "system", "content": system_prompt}] + conversation_history
    payload = {
        "model": TARGET_MODEL,
        "messages": messages,
        "temperature": 0.3
    }

    try:
        response = requests.post(lm_studio_url, json=payload)
        if response.status_code != 200:
            ai_answer = f"LM Studio rejected the request. Details: {response.text}"
        else:
            ai_answer = response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        ai_answer = f"Network Error connecting to LM Studio: {e}"

    chat_session.add_message("assistant", ai_answer)
    chat_session.save()

    context_data = []
    for res in context_results.get("user_entries", []):
        context_data.append({
            "score": round(res['score'], 2),
            "source": res['payload'].get('filename', 'Manual Entry'),
            "content": res['payload'].get('content', '')[:150]
        })
    for res in context_results.get("conversation_archive", []):
        context_data.append({
            "score": round(res['score'], 2),
            "source": "chat_archive",
            "content": res['payload'].get('content', '')[:150]
        })

    return jsonify({
        "answer": ai_answer,
        "context": context_data,
        "history": chat_session.get_history()
    })


def set_model_loaded(loaded: bool):
    global STAY_LOADED
    STAY_LOADED = loaded
    save_settings({"stay_loaded": loaded})
    if loaded:
        print(f"Loading {TARGET_MODEL}...")
        subprocess.run(["lms", "load", TARGET_MODEL], check=False)
        time.sleep(2)
        print(f"{TARGET_MODEL} loaded and staying in memory.")
    else:
        print(f"Unloading {TARGET_MODEL}...")
        subprocess.run(["lms", "unload", TARGET_MODEL], check=False)
        print(f"{TARGET_MODEL} unloaded.")


@app.route('/api/model/loading_mode', methods=['GET', 'PATCH'])
def model_loading_mode():
    if request.method == 'GET':
        return jsonify({"stay_loaded": STAY_LOADED})

    data = request.json
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    stay_loaded = data.get("stay_loaded")
    if stay_loaded is None:
        return jsonify({"error": "stay_loaded field required"}), 400

    set_model_loaded(bool(stay_loaded))
    return jsonify({"stay_loaded": STAY_LOADED})


@app.route('/api/chat/clear', methods=['POST'])
def chat_clear():
    chat_session.clear()
    return jsonify({"status": "success"})


@app.route('/api/chat/history', methods=['GET'])
def chat_history():
    return jsonify(chat_session.get_history())

# Update your existing shutdown behavior to also kill the LM Studio server
def shutdown():
    if hasattr(db, 'client') and db.client:
        print("Closing Qdrant connection...")
        db.client.close()

    print("Shutting down LM Studio server...")
    try:
        if TARGET_MODEL:
            subprocess.run(["lms", "unload", TARGET_MODEL])
        if EMBEDDING_MODEL:
            subprocess.run(["lms", "unload", EMBEDDING_MODEL])
        subprocess.run(["lms", "server", "stop"])
    except FileNotFoundError:
        pass # lms wasn't installed, nothing to shut down

atexit.register(shutdown)

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-

if __name__ == "__main__":

    start_lm_studio()

    app.run(debug=True, use_reloader=False, threaded=True)