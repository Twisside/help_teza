from flask import Flask, render_template, request
from database import QdrantRepo, MongoRepo

app = Flask(__name__)

USE_QDRANT = False

if USE_QDRANT:
    db = QdrantRepo(location="http://localhost:6333")
else:
    db = MongoRepo(uri="mongodb://localhost:27017/try_teza")

db.connect()
@app.route('/', methods=['GET', 'POST'])
def home():
    entry = None
    if request.method == 'POST':
        # 'user_input' matches the 'name' attribute in our HTML input
        entry = request.form.get('user_input')
        db.insert("inputs", {"in":entry})

    return render_template('home.html', entry=entry)


# help

if __name__ == "__main__":
    app.run(debug=True)