"""General SAY community discussions."""

from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from database.db import db
from middleware.auth import cookie_login_required

from models.discussion import DiscussionPost, DiscussionReply
from models.users import User
from models.user_profile import UserProfile


discussion = Blueprint("discussion", __name__)


CATEGORIES = {
    "GENERAL",
    "QUESTION",
    "SUGGESTION",
    "BUG_REPORT",
}


def _pagination():
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
    except (TypeError, ValueError):
        return None

    return (limit, offset) if 1 <= limit <= 50 and 0 <= offset <= 1000000 else None


def _text(data, name, minlen, maxlen):
    value = data.get(name)

    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")

    value = value.strip()

    if not minlen <= len(value) <= maxlen:
        raise ValueError(f"{name} must be {minlen}..{maxlen} characters.")

    return value


def _author(uid):
    user = db.session.get(User, uid)
    profile = UserProfile.query.filter_by(user_id=uid).first()

    return {
        "uid": uid,
        "username": user.name if user else "deleted_user",
        "display_name": (
            profile.display_name
            if profile and profile.display_name
            else (user.name if user else "deleted_user")
        ),
        "avatar_url": (
            f"/api/avatars/{profile.avatar_filename}"
            if profile and profile.avatar_filename
            else None
        ),
    }


def _post_data(post):
    reply_count = db.session.execute(
        db.select(func.count())
        .select_from(DiscussionReply)
        .where(DiscussionReply.post_id == post.id)
    ).scalar_one()

    return {
        "id": post.id,
        "title": post.title if not post.is_deleted else "[Deleted post]",
        "body": post.body if not post.is_deleted else None,
        "category": post.category,
        "is_deleted": post.is_deleted,
        "is_locked": post.is_locked,
        "reply_count": reply_count,
        "author": _author(post.author_uid),
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


def _reply_data(reply):
    return {
        "id": reply.id,
        "post_id": reply.post_id,
        "parent_id": reply.parent_id,
        "body": reply.body if not reply.is_deleted else None,
        "is_deleted": reply.is_deleted,
        "author": _author(reply.author_uid),
        "created_at": reply.created_at.isoformat(),
        "updated_at": reply.updated_at.isoformat(),
    }


def _rate_limited(model, uid, cap):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)

    count = db.session.execute(
        db.select(func.count())
        .select_from(model)
        .where(
            model.author_uid == uid,
            model.created_at >= now
        )
    ).scalar_one()

    return count >= cap


# --------------------------------------------------
# POSTS
# --------------------------------------------------

@discussion.get("/api/discussions")
@cookie_login_required
def list_posts(user):
    paging = _pagination()

    if not paging:
        return jsonify({
            "message": "limit must be 1..50; offset must be nonnegative"
        }), 400

    category = request.args.get("category")

    query = db.select(DiscussionPost)

    if category and category.upper() != "ALL":
        category = category.upper()

        if category not in CATEGORIES:
            return jsonify({"message": "Invalid category."}), 400

        query = query.where(DiscussionPost.category == category)

    rows = db.session.execute(
        query
        .order_by(
            DiscussionPost.created_at.desc(),
            DiscussionPost.id.desc()
        )
        .limit(paging[0])
        .offset(paging[1])
    ).scalars().all()

    count_query = db.select(func.count()).select_from(DiscussionPost)

    if category and category.upper() != "ALL":
        count_query = count_query.where(
            DiscussionPost.category == category.upper()
        )

    total = db.session.execute(count_query).scalar_one()

    return jsonify({
        "total": total,
        "posts": [_post_data(post) for post in rows],
    }), 200


@discussion.post("/api/discussions")
@cookie_login_required
def create_post(user):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "JSON object required."}), 400

    try:
        title = _text(data, "title", 3, 160)
        body = _text(data, "body", 1, 10000)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    category = data.get("category", "GENERAL")

    if not isinstance(category, str) or category.upper() not in CATEGORIES:
        return jsonify({"message": "Invalid discussion category."}), 400

    if _rate_limited(DiscussionPost, user.uid, 5):
        return jsonify({
            "message": "Too many posts. Please try again later."
        }), 429

    post = DiscussionPost(
        author_uid=user.uid,
        title=title,
        body=body,
        category=category.upper(),
    )

    db.session.add(post)
    db.session.commit()

    return jsonify({
        "post": _post_data(post)
    }), 201


@discussion.get("/api/discussions/<int:post_id>")
@cookie_login_required
def get_post(user, post_id):
    post = db.session.get(DiscussionPost, post_id)

    if not post:
        return jsonify({"message": "Discussion not found."}), 404

    return jsonify({
        "post": _post_data(post)
    }), 200


@discussion.patch("/api/discussions/<int:post_id>")
@cookie_login_required
def edit_post(user, post_id):
    post = db.session.get(DiscussionPost, post_id)

    if not post or post.is_deleted:
        return jsonify({"message": "Discussion not found."}), 404

    if post.author_uid != user.uid and user.privilege != "admin":
        return jsonify({"message": "Not your discussion."}), 403

    data = request.get_json(silent=True)

    allowed_fields = {"title", "body", "category", "is_locked"}

    if not isinstance(data, dict) or not data or not set(data).issubset(allowed_fields):
        return jsonify({"message": "Invalid changes."}), 400

    try:
        if "title" in data:
            post.title = _text(data, "title", 3, 160)

        if "body" in data:
            post.body = _text(data, "body", 1, 10000)

    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    if "category" in data:
        category = data["category"]

        if not isinstance(category, str) or category.upper() not in CATEGORIES:
            return jsonify({"message": "Invalid category."}), 400

        post.category = category.upper()

    if "is_locked" in data:
        if user.privilege != "admin":
            return jsonify({"message": "Moderator access required."}), 403

        if type(data["is_locked"]) is not bool:
            return jsonify({"message": "is_locked must be boolean."}), 400

        post.is_locked = data["is_locked"]

    db.session.commit()

    return jsonify({"post": _post_data(post)}), 200


@discussion.delete("/api/discussions/<int:post_id>")
@cookie_login_required
def delete_post(user, post_id):
    post = db.session.get(DiscussionPost, post_id)

    if not post:
        return jsonify({"message": "Discussion not found."}), 404

    if post.author_uid != user.uid and user.privilege != "admin":
        return jsonify({"message": "Not your discussion."}), 403

    post.is_deleted = True
    post.body = ""

    db.session.commit()

    return jsonify({"message": "Discussion deleted."}), 200


# --------------------------------------------------
# REPLIES
# --------------------------------------------------

@discussion.get("/api/discussions/<int:post_id>/replies")
@cookie_login_required
def list_replies(user, post_id):
    post = db.session.get(DiscussionPost, post_id)

    if not post:
        return jsonify({"message": "Discussion not found."}), 404

    paging = _pagination()

    if not paging:
        return jsonify({"message": "Invalid pagination."}), 400

    rows = db.session.execute(
        db.select(DiscussionReply)
        .where(DiscussionReply.post_id == post_id)
        .order_by(
            DiscussionReply.created_at,
            DiscussionReply.id
        )
        .limit(paging[0])
        .offset(paging[1])
    ).scalars().all()

    total = db.session.execute(
        db.select(func.count())
        .select_from(DiscussionReply)
        .where(DiscussionReply.post_id == post_id)
    ).scalar_one()

    return jsonify({
        "post_id": post_id,
        "total": total,
        "replies": [_reply_data(reply) for reply in rows],
    }), 200


@discussion.post("/api/discussions/<int:post_id>/replies")
@cookie_login_required
def create_reply(user, post_id):
    post = db.session.get(DiscussionPost, post_id)

    if not post or post.is_deleted:
        return jsonify({"message": "Discussion not found."}), 404

    if post.is_locked:
        return jsonify({"message": "Discussion is locked."}), 409

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "JSON object required."}), 400

    try:
        body = _text(data, "body", 1, 10000)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    parent_id = data.get("parent_id")

    if parent_id is not None:
        if type(parent_id) is not int:
            return jsonify({"message": "parent_id must be an integer."}), 400

        parent = db.session.get(DiscussionReply, parent_id)

        if not parent or parent.post_id != post_id:
            return jsonify({
                "message": "Parent reply does not belong to this discussion."
            }), 400

    if _rate_limited(DiscussionReply, user.uid, 15):
        return jsonify({
            "message": "Too many replies. Please try again later."
        }), 429

    reply = DiscussionReply(
        post_id=post_id,
        parent_id=parent_id,
        author_uid=user.uid,
        body=body,
    )

    db.session.add(reply)
    db.session.commit()

    return jsonify({
        "reply": _reply_data(reply)
    }), 201


@discussion.patch("/api/discussions/replies/<int:reply_id>")
@cookie_login_required
def edit_reply(user, reply_id):
    reply = db.session.get(DiscussionReply, reply_id)

    if not reply or reply.is_deleted:
        return jsonify({"message": "Reply not found."}), 404

    if reply.author_uid != user.uid and user.privilege != "admin":
        return jsonify({"message": "Not your reply."}), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data or set(data) != {"body"}:
        return jsonify({"message": "Invalid changes."}), 400

    try:
        reply.body = _text(data, "body", 1, 10000)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    db.session.commit()

    return jsonify({
        "reply": _reply_data(reply)
    }), 200


@discussion.delete("/api/discussions/replies/<int:reply_id>")
@cookie_login_required
def delete_reply(user, reply_id):
    reply = db.session.get(DiscussionReply, reply_id)

    if not reply:
        return jsonify({"message": "Reply not found."}), 404

    if reply.author_uid != user.uid and user.privilege != "admin":
        return jsonify({"message": "Not your reply."}), 403

    reply.is_deleted = True
    reply.body = ""

    db.session.commit()

    return jsonify({"message": "Reply deleted."}), 200