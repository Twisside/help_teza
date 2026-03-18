import atexit
import os
import subprocess
import time
import requests
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from chunker import DocumentChunker
from database import QdrantRepo



app = Flask(__name__)

# --- Setup Local File System Storage ----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---=-
# will change it so search nad select through the file system
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# -=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---


db = QdrantRepo(use_qwen=False) #8187
db.connect()

doc_chunker = DocumentChunker()


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        entry = request.form.get('user_input')

        # 1. Get raw tags string, split by comma, and clean up whitespace
        raw_tags = request.form.get('tags', '')
        tags_list = [t.strip() for t in raw_tags.split(',') if t.strip()]
        if not tags_list:
            tags_list = ['untagged'] # Default if left empty

        if entry:
            # Save 'tags' as a list
            db.insert("user_entries", {"content": entry, "tags": tags_list})
        return redirect(url_for('home'))

    query = request.args.get('search')

    # 2. Handle multiple search tags
    search_tags_raw = request.args.get('search_tags', '')
    search_tags_list = [t.strip() for t in search_tags_raw.split(',') if t.strip()]

    if query:
        search_results = db.search("user_entries", query, search_tags=search_tags_list if search_tags_list else None, limit=5)
        all_entries = [{"id": r['id'], **r['payload'], "score": r['score']} for r in search_results]
    else:
        all_entries = db.get_all("user_entries")

    return render_template('home.html', entries=all_entries, is_search=bool(query))


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('home'))

    file = request.files['file']

    # 3. Apply the same tag parsing to file uploads
    raw_tags = request.form.get('tags', '')
    tags_list = [t.strip() for t in raw_tags.split(',') if t.strip()]
    if not tags_list:

        #TODO:
        # Add automatic tagging
        tags_list = ['untagged']

    if file.filename == '':
        return redirect(url_for('home'))

# ---------------------------there will be a better file system-----------------
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
# ------------------------------------------------------------------------------
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            print(f"Chunking {filename} with hybrid paragraph chunker...")
            # Here is where your new DocumentChunker class steps in!
            text_chunks = doc_chunker.chunk_document(content)
            print(f"Created {len(text_chunks)} chunks. Embedding now...")

            for i, chunk in enumerate(text_chunks):
                print(f"Embedding chunk {i + 1}/{len(text_chunks)}...")
                # Save each chunk to Qdrant with the exact same metadata
                db.insert("user_entries", {
                    "content": chunk,
                    "tags": tags_list,
                    "filename": filename,
                    "filepath": filepath,
                    "chunk_index": i
                })

            print("Upload and embedding complete!")

        except Exception as e:
            print(f"Error reading or embedding file {filename}: {e}")
    return redirect(url_for('home'))

@app.route('/db/update/<collection>/<item_id>', methods=['POST'])
def updateitem(collection, item_id):
    new_text = request.form.get('updated_content')
    if new_text:
        db.update(collection, item_id, {"content": new_text})

    # Send user back to the home page list
    return redirect(url_for('home'))


@app.route('/db/delete/<collection>/<item_id>')
def deleteitem(collection, item_id):
    db.delete(collection, item_id)
    return redirect(url_for('home'))


@app.route('/db/read/<collection>')
def readdb(collection):
    entries = db.get_all(collection)

    return entries


# -------------------------------------

# LM Studio CLI Integration

# Feature flag for your future model.
# Once you download a model (e.g., 'lms get qwen3-coder'), put its name here.

#  TODO:
#   Will make a select menu of models in the future

TARGET_MODEL = os.getenv("TARGET_MODEL")

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

    except FileNotFoundError:
        print("\nERROR: 'lms' command not found.")
        print("Please install LM Studio and run 'lms bootstrap' in your terminal.\n")
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Failed to load model {TARGET_MODEL}. Is it downloaded?\nDetails: {e}\n")


@app.route('/ask', methods=['POST'])
def ask_ai():
    user_query = request.form.get('question')
    if not user_query:
        return redirect(url_for('home'))

    # 1. RETRIEVE: Get the most relevant chunks from Qdrant
    # Limiting the resources if the score is to low, but if the low score id the highest, use them
    # 1. Get initial results
    search_results = db.search("user_entries", user_query, limit=5)
    high_quality = [res for res in search_results if res['score'] > 0.5]
    new_results = high_quality if len(high_quality) >= 3 else search_results[:3]

    # 2. AUGMENT: Combine the retrieved chunks into a single text block
    context_texts = [res['payload']['content'] for res in new_results]
    context_string = "\n\n---\n\n".join(context_texts)

    # 3. GENERATE: Build the prompt and send it to LM Studio
    system_prompt = "You are a helpful assistant. Answer the user's question based ONLY on the provided context. If the answer is not in the context, say 'I don't know based on my current documents.'"

    user_prompt = f"Context:\n{context_string}\n\nQuestion: {user_query}"

    lm_studio_url = "http://127.0.0.1:1234/v1/chat/completions"
    payload = {
        "model": os.getenv("TARGET_MODEL"), # LM Studio ignores this name but requires the field
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3 # Keep it low so the model sticks strictly to the facts
    }

    try:
        response = requests.post(lm_studio_url, json=payload)

        # 2. Check for errors and grab the EXACT message from LM Studio
        if response.status_code != 200:
            ai_answer = f"LM Studio rejected the request. Details: {response.text}"
        else:
            ai_answer = response.json()['choices'][0]['message']['content']

    except requests.exceptions.RequestException as e:
        ai_answer = f"Network Error connecting to LM Studio: {e}"

    # Fetch all entries to keep the main list populated
    all_entries = db.get_all("user_entries")

    return render_template(
        'home.html',
        entries=all_entries,
        is_search=False,
        ai_answer=ai_answer,
        user_query=user_query,
        retrieved_context=new_results
    )


# Update your existing shutdown behavior to also kill the LM Studio server
def shutdown():
    if hasattr(db, 'client') and db.client:
        print("Closing Qdrant connection...")
        db.client.close()

    print("Shutting down LM Studio server...")
    try:
        if TARGET_MODEL:
            subprocess.run(["lms", "unload", TARGET_MODEL])
        subprocess.run(["lms", "server", "stop"])
    except FileNotFoundError:
        pass # lms wasn't installed, nothing to shut down

atexit.register(shutdown)

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-

if __name__ == "__main__":

    start_lm_studio()

    app.run(debug=True, use_reloader=False)