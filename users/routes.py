from flask import Blueprint, request

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

@users.route("/me/name", methods=["PUT"])
@login_required
def update_my_name(user):
    from flask import request

    data = request.get_json()

    if not data or not isinstance(data.get("name"), str):
        return {"message": "Name is required"}, 400

    name = data["name"].strip()

    if not name:
        return {"message": "Name cannot be empty"}, 400

    if len(name) > 100:
        return {"message": "Name cannot exceed 100 characters"}, 400

    existing_user = User.query.filter(
        User.name == name,
        User.uid != user.uid
    ).first()

    if existing_user:
        return {"message": "This name is already taken"}, 409

    user.name = name
    db.session.commit()

    return {
        "message": "Name updated successfully",
        "user": {
            "uid": user.uid,
            "name": user.name,
            "email": user.email,
            "privilege": user.privilege
        }
    }, 200

@users.route("/change-password", methods=["PUT"])
@login_required
def change_password(user):
    data = request.get_json()

    if not data:
        return {"message": "Request body is required"}, 400

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return {
            "message": "Current password and new password are required"
        }, 400

    if len(new_password) < 8:
        return {
            "message": "New password must be at least 8 characters long"
        }, 400

    if not check_password_hash(user.password, current_password):
        return {"message": "Current password is incorrect"}, 400

    
    user.password = generate_password_hash(new_password)
    db.session.commit()

    return {"message": "Password updated successfully"}, 200