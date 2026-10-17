from flask import Blueprint

from database.db import db
from models.users import User

from middleware.auth import admin_required
from middleware.auth import login_required

users = Blueprint("users", __name__)


@users.route("/users", methods=["GET"])
@admin_required
def get_users(admin):
    users_list = User.query.all()

    return {
        "users": [
            {
                "uid": user.uid,
                "name": user.name,
                "email": user.email,
                "privilege": user.privilege
            }
            for user in users_list
        ]
    }, 200


@users.route("/users/<int:user_id>", methods=["GET"])
# @admin_required
def get_user(user_id):

    user = User.query.get(user_id)

    return {
        "user_id": user.uid,
        "name": user.name,
        "email": user.email
    }

@users.route("/users/make-admin/<int:user_id>", methods=["PUT"])
@admin_required
def make_admin(user_id):

    user = User.query.get(user_id)

    if user is None:
        return {
            "message": "User not found"
        }, 404

    user.privilege = "admin"

    db.session.commit()

    return {
        "message": "Role changed successfully"
    }
    
@users.route("/me", methods=["GET"])
@login_required
def me(user):

    return {
        "uid": user.uid,
        "name": user.name,
        "email": user.email,
        "privilege": user.privilege
    }


@users.route("/users/delete/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):

    user = User.query.get(user_id)

    if user is None:
        return {
            "message": "User not found"
        }, 404

    db.session.delete(user)
    db.session.commit()

    return {
        "message": "User deleted successfully"
    }, 200

@users.route("/me", methods=["PUT"])
@login_required
def update_my_username(user):
    from flask import request
    from sqlalchemy.exc import IntegrityError

    data = request.get_json(silent=True)
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 100:
        return {"message": "Username must be 3–100 characters"}, 400

    name = name.strip()
    existing = User.query.filter(User.name == name, User.uid != user.uid).first()
    if existing:
        return {"message": "That username is already taken"}, 409

    user.name = name
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"message": "That username is already taken"}, 409

    return {"message": "Username updated successfully", "name": user.name}, 200
