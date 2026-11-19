"""SAY-local usernames and administrative user listing. No password routes."""
from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from database.db import db
from middleware.auth import login_required, admin_required
from models.users import User
from models.codeforces_oidc_identity import CodeforcesOidcIdentity

users = Blueprint('users', __name__)


def public(user):
    return {'uid': user.uid, 'name': user.name, 'privilege': user.privilege}


@users.get('/me')
@login_required
def me(user):
    ident = CodeforcesOidcIdentity.query.filter_by(uid=user.uid).first()
    return {**public(user), 'codeforces': ident.public() if ident else None}, 200


@users.get('/users')
@admin_required
def get_users(admin):
    return {'users': [public(u) for u in User.query.order_by(User.uid).limit(200).all()]}, 200


@users.get('/users/<int:user_id>')
@login_required
def get_user(viewer, user_id):
    user = db.session.get(User, user_id)
    return (public(user), 200) if user else ({'message':'User not found'}, 404)


@users.put('/me/name')
@login_required
def update_my_name(user):
    data = request.get_json(silent=True)
    name = data.get('name','').strip() if isinstance(data,dict) and isinstance(data.get('name'),str) else ''
    if not 3 <= len(name) <= 100:
        return {'message':'SAY username must be 3..100 characters'}, 400
    user.name = name
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'message':'SAY username is already taken'}, 409
    return {'user':public(user)}, 200


@users.put('/users/make-admin/<int:user_id>')
@admin_required
def make_admin(admin, user_id):
    target = db.session.get(User, user_id)
    if not target:return {'message':'User not found'}, 404
    target.privilege = 'admin'
    db.session.commit()
    return {'message':'Role changed successfully'}, 200


@users.delete('/users/delete/<int:user_id>')
@admin_required
def delete_user(admin, user_id):
    return {'message':'Account deletion requires a reviewed data-retention process (forum/history foreign keys)'}, 409


@users.put('/change-password')
@login_required
def password_retired(user):
    return {'message':'SAY authentication is Codeforces-only; passwords are unsupported'}, 410
