"""Authentication helpers for SAY."""

import hashlib
import secrets
from functools import wraps

from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from database.db import db
from models.session import Session
from models.users import User


_TOKEN_SALT = "say-api-session-v1"


def token_digest(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=_TOKEN_SALT
    )


def issue_session_token(uid: int) -> str:
    return _serializer().dumps({
        "uid": uid,
        "nonce": secrets.token_urlsafe(24)
    })


def bearer_token() -> str | None:
    authorization = request.headers.get(
        "Authorization", ""
    ).strip()

    if not authorization:
        return None

    if authorization.lower().startswith("bearer "):
        authorization = authorization[7:].strip()

    # Accept old raw Authorization header format too.
    if authorization and " " not in authorization:
        return authorization

    return None


def current_user() -> User | None:
    token = bearer_token()

    if token is None:
        return None

    try:
        payload = _serializer().loads(
            token,
            max_age=current_app.config[
                "SESSION_MAX_AGE_SECONDS"
            ]
        )
    except (BadSignature, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    uid = payload.get("uid")

    if not isinstance(uid, int) or isinstance(uid, bool):
        return None

    active_session = Session.query.filter_by(
        uid=uid,
        token=token_digest(token)
    ).first()

    if active_session is None:
        return None

    return db.session.get(User, uid)


def login_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        user = current_user()

        if user is None:
            return {
                "message": (
                    "Authentication required or session expired"
                )
            }, 401

        return function(user, *args, **kwargs)

    return decorated


def admin_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        user = current_user()

        if user is None:
            return {
                "message": (
                    "Authentication required or session expired"
                )
            }, 401

        if user.privilege != "admin":
            return {
                "message": "Admin access required"
            }, 403

        return function(user, *args, **kwargs)

    return decorated