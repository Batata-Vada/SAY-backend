from flask import Flask

from database.db import db

from auth.routes import auth
from users.routes import users

from models.users import User


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"

db.init_app(app)

with app.app_context():
    db.create_all()

app.register_blueprint(auth)
app.register_blueprint(users)


@app.route("/")
def hello():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    app.run(debug=True)