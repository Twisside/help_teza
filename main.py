import atexit
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

app = Flask(__name__)

# --- Setup Local File System Storage ----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---=-
# will change it so search nad select through the file system
ALLOWED_EXTENSIONS = {'.txt', '.md', '.pdf', '.py', '.js', '.cs'}
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
TARGET_MODEL = "google/gemma-3-1b"
EMBEDDING_MODEL ="text-embedding-embeddinggemma-300m" #< ====================================================================
# -=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---


db = QdrantRepo(use_qwen=False) #8187
db.connect()

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

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file detected."}), 400

    file = request.files['file']

    # Apply the same tag parsing to file uploads
    raw_tags = request.form.get('tags', '')
    tags_list = [t.strip() for t in raw_tags.split(',') if t.strip()]

    if not tags_list:
        # Automatic tagging implementation
        try:
            # We read the file content early to generate the tags
            file.seek(0)
            content_preview = file.read().decode('utf-8', errors='ignore')[:1000]
            file.seek(0)  # Reset file pointer for the saving process later

            print("No tags provided. Generating automatic tags...")
            tags_list = generate_tags_with_llm(content_preview)
        except Exception as e:
            print(f"Failed to auto-generate tags: {e}")
            tags_list = ['untagged']

    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400

# ---------------------------there will be a better file system-----------------
    if file:
        filename = secure_filename(file.filename)
        _, ext = os.path.splitext(filename)

        if ext.lower() not in ALLOWED_EXTENSIONS:
            print(f"Blocked upload: Unsupported file type '{ext}'")
            # Redirect back home, but attach the error to the URL
            return jsonify({"error": f"Unsupported file: {ext}. Allowed: PDF, TXT, MD, PY, JS, CS"}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
# ------------------------------------------------------------------------------
        try:
            start_time = time.time()
            print(f"Processing {filename} with UniversalParser...")

            # 1. Let the UniversalParser handle opening the file correctly
            # based on its extension, extracting the text, and chunking it.
            text_chunks = doc_parser.process_file(filepath)

            if not text_chunks:
                print(f"Warning: No valid text could be extracted from {filename}")
                return jsonify({"error": "Could not extract readable text from that file."}), 400

            print(f"Created {len(text_chunks)} chunks. Embedding now...")

            for i, chunk in enumerate(text_chunks):
                print(f"Embedding chunk {i + 1}/{len(text_chunks)}...")
                db.insert("user_entries", {
                    "content": chunk,
                    "tags": tags_list,
                    "filename": filename,
                    "filepath": filepath,
                    "chunk_index": i
                })
            process_time = time.time() - start_time
            print(f">>>Upload and embedding complete in {process_time:.2f} seconds")
            return jsonify({"status": "success", "message": f"{filename} embedded in {process_time:.2f}s!"})

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
bg_indexer = UniversalBackgroundIndexer(db, doc_chunker)

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
    """Starts the LM Studio local server and loads the specified model."""
    print("Starting LM Studio API server in the background...")
    try:
        # Start the server (non-blocking)
        subprocess.Popen(["lms", "server", "start"])

        # Give the server a few seconds to initialize
        time.sleep(3)

        if TARGET_MODEL:
            print(f"Loading SLM: {TARGET_MODEL}...")
            # check=True ensures Python throws an error if the model fails to load
            subprocess.run(["lms", "load", TARGET_MODEL], check=True)
            print(f"{TARGET_MODEL} is locked and loaded!")
        else:
            print("No target model specified. LM Studio server is running empty.")


        if EMBEDDING_MODEL:
            print(f"Loading Embedding Model: {EMBEDDING_MODEL}...")
            subprocess.run(["lms", "load", EMBEDDING_MODEL], check=True)
            print(f"{EMBEDDING_MODEL} loaded!")
        else:
            print("No target model specified. LM Studio server is running empty.")

    except FileNotFoundError:
        print("\nERROR: 'lms' command not found.")
        print("Please install LM Studio and run 'lms bootstrap' in your terminal.\n")
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Failed to load model {TARGET_MODEL}. Is it downloaded?\nDetails: {e}\n")


@app.route('/ask', methods=['POST'])
def ask_ai():
    user_query = request.form.get('question')
    if not user_query:
        # Changed from redirect to jsonify
        return jsonify({"error": "No query provided"}), 400

    # 1. RETRIEVE
    search_results = db.search("user_entries", user_query, limit=5)
    high_quality = [res for res in search_results if res['score'] > 0.5]
    new_results = high_quality if len(high_quality) >= 3 else search_results[:3]

    # 2. AUGMENT
    context_items = []
    for res in new_results:
        content = res['payload']['content']
        date = res['payload'].get('timestamp', 'Unknown Date')
        source = res['payload'].get('filename', 'Manual Entry')

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

    app.run(debug=True, use_reloader=False)