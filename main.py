import os
import subprocess
import time

from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

from database import QdrantRepo



app = Flask(__name__)

# --- Setup Local File System Storage ----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---=-
# will change it so search nad select through the file system
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# -=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=----=-=-=-=-=-=---=-==-=-=-==-=-=-=-=-=-=---


db = QdrantRepo(use_qwen=True) #8187
db.connect()


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
        tags_list = ['untagged']

    if file.filename == '':
        return redirect(url_for('home'))

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            db.insert("user_entries", {
                "content": content,
                "tags": tags_list, # Saved as a list here too
                "filename": filename,
                "filepath": filepath
            })
        except Exception as e:
            print(f"Error reading file {filename}: {e}")

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
import atexit

# Shutdown for the db, just to keep all safe and
# without any risks of crashing it
def shutdown():
    if hasattr(db, 'client') and db.client:
        print("Closing database connection...")
        db.client.close()

atexit.register(shutdown)

# -------------------------------------



# LM Studio CLI Integration

# Feature flag for your future model.
# Once you download a model (e.g., 'lms get qwen3-coder'), put its name here.
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
    app.run(debug=True, use_reloader=False)