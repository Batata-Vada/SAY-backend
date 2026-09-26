from functools import wraps
from flask import request

from models.session import Session
from models.users import User


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        token = request.headers.get("Authorization")

        if not token:
            return {
                "message": "Authentication required"
            }, 401

        session = Session.query.filter_by(
            token=token
        ).first()

        if session is None:
            return {
                "message": "Invalid session"
            }, 401

        user = User.query.get(session.uid)

        if user is None:
            return {
                "message": "User not found"
            }, 401

        return f(user, *args, **kwargs)

    return decorated_function


def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        token = request.headers.get("Authorization")

        if not token:
            return {
                "message": "Authentication required"
            }, 401

        session = Session.query.filter_by(
            token=token
        ).first()

        if session is None:
            return {
                "message": "Invalid session"
            }, 401

        user = User.query.get(session.uid)

        if user is None:
            return {
                "message": "User not found"
            }, 401

        if user.privilege != "admin":
            return {
                "message": "Admin access required"
            }, 403

        return f(*args, **kwargs)

    return decorated_function