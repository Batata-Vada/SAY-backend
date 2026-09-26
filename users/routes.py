from flask import Blueprint

from database.db import db
from models.users import User

from middleware.auth import admin_required
from middleware.auth import login_required

users = Blueprint("users", __name__)


@users.route("/users", methods=["GET"])
def get_users():

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
    }


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