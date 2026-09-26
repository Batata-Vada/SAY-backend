import bcrypt
import secrets

from flask import Blueprint, request

from database.db import db

from models.users import User
from models.session import Session

from middleware.auth import login_required


auth = Blueprint("auth", __name__)


@auth.route("/register", methods=["POST"])
def register():

    data = request.json

    name = data["name"]
    email = data["email"]
    password = data["password"]

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )

    if name == "master":
        privilege = "admin"
    else:
        privilege = "user"

    user = User(
        name=name,
        email=email,
        password=password_hash.decode("utf-8"),
        privilege=privilege
    )

    db.session.add(user)
    db.session.commit()

    return {
        "message": "User registered successfully"
    }, 201


@auth.route("/login", methods=["POST"])
def login():

    data = request.json

    name = data["name"]
    password = data["password"]

    user = User.query.filter_by(name=name).first()

    if user is None:
        return {
            "message": "Invalid credentials"
        }, 401

    password_correct = bcrypt.checkpw(
        password.encode("utf-8"),
        user.password.encode("utf-8")
    )

    if not password_correct:
        return {
            "message": "Invalid credentials"
        }, 401

    token = secrets.token_urlsafe(32)

    session = Session(
        uid=user.uid,
        token=token
    )

    db.session.add(session)
    db.session.commit()

    return {
        "message": "Login successful",
        "token": token
    }, 200

@auth.route("/logout", methods=["POST"])
@login_required
def logout(user):

    token = request.headers.get("Authorization")

    session = Session.query.filter_by(
        token=token
    ).first()

    db.session.delete(session)
    db.session.commit()

    return {
        "message": "Logged out successfully"
    }, 200