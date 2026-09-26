from flask import Flask
from flask_cors import CORS

from database.db import db

from auth.routes import auth
from users.routes import users

from models.users import User
from models.session import Session


app = Flask(__name__)

CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"

db.init_app(app)

with app.app_context():
    db.create_all()

app.register_blueprint(auth)
app.register_blueprint(users)


@app.route("/")
def hello():

    return {
        "message": "Hello, World!"
    }


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )