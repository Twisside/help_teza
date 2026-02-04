from flask import Flask, render_template, request, redirect, url_for

from database import QdrantRepo, MongoRepo

app = Flask(__name__)
db = QdrantRepo() # use_qwen=False
db.connect()


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        entry = request.form.get('user_input')
        if entry:
            db.insert("user_entries", {"content": entry})
        # Always redirect after a POST to prevent "form resubmission" popups
        return redirect(url_for('home'))

    # Read the data to display it
    all_entries = db.get_all("user_entries")
    return render_template('home.html', entries=all_entries)


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

# Shutdown behavior
def shutdown():
    if hasattr(db, 'client') and db.client:
        print("Closing database connection...")
        db.client.close()

atexit.register(shutdown)

# ------------------------------------- 

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)