"""SAY registration, login, and logout."""

import re
import bcrypt

from flask import Blueprint, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database.db import db
from middleware.auth import (
    bearer_token,
    issue_session_token,
    login_required,
    token_digest,
)
from models.session import Session
from models.users import User


auth = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _json_object():
    data = request.get_json(silent=True)

    return data if isinstance(data, dict) else None


@auth.route("/register", methods=["POST"])
def register():
    data = _json_object()

    if data is None:
        return {"message": "A JSON object is required"}, 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if (
        not isinstance(name, str)
        or not 3 <= len(name.strip()) <= 100
    ):
        return {
            "message": "Name must be 3–100 characters"
        }, 400

    name = name.strip()

    if (
        not isinstance(email, str)
        or len(email.strip()) > 120
    ):
        return {"message": "Invalid email"}, 400

    email = email.strip().lower()

    if not _EMAIL_RE.fullmatch(email):
        return {"message": "Invalid email"}, 400

    if not isinstance(password, str):
        return {
            "message": "Password must be a string"
        }, 400

    password_bytes = password.encode("utf-8")

    if (
        len(password_bytes) < 8
        or len(password_bytes) > 72
    ):
        return {
            "message": "Password must be 8–72 UTF-8 bytes"
        }, 400

    existing = User.query.filter(
        or_(
            User.name == name,
            User.email == email
        )
    ).first()

    if existing is not None:
        return {
            "message": "Name or email is already registered"
        }, 409

    user = User(
        name=name,
        email=email,
        password=bcrypt.hashpw(
            password_bytes,
            bcrypt.gensalt()
        ).decode("utf-8"),
        privilege="user"
    )

    try:
        db.session.add(user)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return {
            "message": "Name or email is already registered"
        }, 409

    except SQLAlchemyError:
        db.session.rollback()
        return {
            "message": "Registration failed"
        }, 500

    return {
        "message": "User registered successfully",
        "uid": user.uid
    }, 201


@auth.route("/login", methods=["POST"])
def login():
    data = _json_object()

    if data is None:
        return {"message": "A JSON object is required"}, 400

    name = data.get("name")
    password = data.get("password")

    if (
        not isinstance(name, str)
        or not isinstance(password, str)
    ):
        return {
            "message": "Name and password are required"
        }, 400

    name = name.strip()
    password_bytes = password.encode("utf-8")

    if (
        not name
        or not password_bytes
        or len(password_bytes) > 72
    ):
        return {"message": "Invalid credentials"}, 401

    user = User.query.filter_by(name=name).first()

    if user is None:
        return {"message": "Invalid credentials"}, 401

    try:
        valid = bcrypt.checkpw(
            password_bytes,
            user.password.encode("utf-8")
        )
    except (ValueError, TypeError):
        valid = False

    if not valid:
        return {"message": "Invalid credentials"}, 401

    token = issue_session_token(user.uid)

    try:
        db.session.add(
            Session(
                uid=user.uid,
                token=token_digest(token)
            )
        )
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Login failed"}, 500

    return {
        "message": "Login successful",
        "token": token,
        "token_type": "Bearer"
    }, 200


@auth.route("/logout", methods=["POST"])
@login_required
def logout(user):
    token = bearer_token()

    active_session = Session.query.filter_by(
        uid=user.uid,
        token=token_digest(token)
    ).first()

    if active_session is not None:
        db.session.delete(active_session)
        db.session.commit()

    return {
        "message": "Logged out successfully"
    }, 200

@auth.route("/change-password", methods=["PUT"])
@login_required
def change_password(user):
    data = _json_object()
    if data is None:
        return {"message": "A JSON object is required"}, 400

    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if not isinstance(current_password, str) or not isinstance(new_password, str):
        return {"message": "Current and new passwords are required"}, 400

    current_bytes = current_password.encode("utf-8")
    new_bytes = new_password.encode("utf-8")
    if len(current_bytes) > 72 or not 8 <= len(new_bytes) <= 72:
        return {"message": "New password must be 8–72 UTF-8 bytes"}, 400

    try:
        valid = bcrypt.checkpw(current_bytes, user.password.encode("utf-8"))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        return {"message": "Current password is incorrect"}, 401

    user.password = bcrypt.hashpw(new_bytes, bcrypt.gensalt()).decode("utf-8")
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Could not update password"}, 500

    return {"message": "Password updated successfully"}, 200
