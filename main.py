from flask import Flask
from flask_cors import CORS

from database.db import db

from auth.routes import auth
from users.routes import users

# Import models before db.create_all()
from models.users import User
from models.session import Session
from models.problem import Problem

from problem_stats.sync import sync_all


app = Flask(__name__)

CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"

db.init_app(app)


# Create database tables
with app.app_context():
    db.create_all()


# Register blueprints
app.register_blueprint(auth)
app.register_blueprint(users)


@app.route("/")
def hello():
    return {
        "message": "Hello, World!"
    }


@app.cli.command("sync-problems")
def sync_problems_command():
    """Fetch problem metadata from all platforms."""

    results = sync_all()

    print()
    print("Sync results:")
    print(results)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )