from flask import Flask, render_template, request
from database import QdrantRepo, MongoRepo

app = Flask(__name__)

USE_QDRANT = True

if USE_QDRANT:
    db = QdrantRepo()
else:
    db = MongoRepo(uri="mongodb://localhost:27017/try_teza")

db.connect()
@app.route('/', methods=['GET', 'POST'])
def home():
    entry = None
    if request.method == 'POST':
        # 'user_input' matches the 'name' attribute in our HTML input
        entry = request.form.get('user_input')
        db.insert("user_entries", {"content":entry})

    return render_template('home.html', entry=entry)


@app.route('/db/')
def lookdb():
    entries = db.get_all("user_entries")

    return entries

import atexit

# Shutdown behavior
def shutdown():
    if hasattr(db, 'client') and db.client:
        print("Closing database connection...")
        db.client.close()

atexit.register(shutdown)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)