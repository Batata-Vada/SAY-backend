# backend/submissions/routes.py

import os
import re

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError

from database.db import db
from models.users import User
from models.submission import Submission
from middleware.auth import login_required


submissions = Blueprint("submissions", __name__)

LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "cpp": ".cpp"
}


def make_slug(title):
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())
    return slug.strip("_") or "question"


@submissions.route("/submit", methods=["POST"])
@login_required
def submit(user):
    data = request.get_json(silent=True) or {}

    question_id = data.get("question_id")
    question_title = data.get("question_title")
    language = data.get("language")
    code = data.get("code")

    if (
        not isinstance(question_id, int)
        or isinstance(question_id, bool)
        or question_id <= 0
    ):
        return jsonify({
            "message": "Invalid question_id"
        }), 400

    if language not in LANGUAGE_EXTENSIONS:
        return jsonify({
            "message": "Language must be python or cpp"
        }), 400

    if not isinstance(code, str) or not code.strip():
        return jsonify({
            "message": "Code cannot be empty"
        }), 400

    if not isinstance(question_title, str):
        return jsonify({
            "message": "question_title is required"
        }), 400

    # Resolve the authenticated user's ID.
    # This assumes login_required passes a User object.
    uid = user.uid

    slug = make_slug(question_title)
    extension = LANGUAGE_EXTENSIONS[language]

    root_dir = current_app.config.get(
        "SUBMISSIONS_DIR",
        os.path.join(current_app.instance_path, "submissions")
    )

    user_dir = os.path.join(root_dir, f"user_{uid}")
    os.makedirs(user_dir, exist_ok=True)

    filename = None
    filepath = None

    # Find the next available filename.
    for index in range(1_000_000):
        candidate = f"{slug}_{index:03d}{extension}"
        candidate_path = os.path.join(user_dir, candidate)

        try:
            with open(
                candidate_path,
                "x",
                encoding="utf-8"
            ) as source_file:
                source_file.write(code)

            filename = candidate
            filepath = candidate_path
            break

        except FileExistsError:
            continue

    if filepath is None:
        return jsonify({
            "message": "Unable to allocate submission filename"
        }), 500

    try:
        submission = Submission(
            uid=uid,
            question_id=question_id,
            language=language,
            filename=filename
        )

        db.session.add(submission)
        db.session.commit()

        return jsonify({
            "message": "Submission saved successfully",
            "submission_id": submission.id,
            "question_id": submission.question_id,
            "language": submission.language,
            "filename": submission.filename
        }), 201

    except SQLAlchemyError:
        db.session.rollback()

        try:
            os.remove(filepath)
        except OSError:
            current_app.logger.exception(
                "Failed to remove unrecorded submission file"
            )

        current_app.logger.exception(
            "Failed to save submission"
        )

        return jsonify({
            "message": "Failed to save submission"
        }), 500


@submissions.route("/submissions", methods=["GET"])
@login_required
def get_submissions(user):
    # The authenticated user comes from the token middleware.
    query = Submission.query.filter_by(uid=user.uid)

    # Optional language filter: cpp or python
    language = request.args.get("language", "").strip().lower()

    if language:
        if language not in ("cpp", "python"):
            return {
                "message": "Invalid language. Use 'cpp' or 'python'."
            }, 400

        query = query.filter_by(language=language)

    # Optional question filter
    question_id = request.args.get("question_id")

    if question_id is not None:
        try:
            question_id = int(question_id)
        except (TypeError, ValueError):
            return {"message": "question_id must be an integer."}, 400

        if question_id <= 0:
            return {"message": "question_id must be positive."}, 400

        query = query.filter_by(question_id=question_id)

    # Pagination
    try:
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return {"message": "limit and offset must be integers."}, 400

    if not 1 <= limit <= 100:
        return {"message": "limit must be between 1 and 100."}, 400

    if offset < 0:
        return {"message": "offset cannot be negative."}, 400

    # Count after applying filters, but before pagination
    total = query.count()

    # Most recent submissions first
    submissions_list = (
        query
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "submissions": [
            {
                "id": submission.id,
                "question_id": submission.question_id,
                "language": submission.language,
                "filename": submission.filename,
                "created_at": (
                    submission.created_at.isoformat()
                    if submission.created_at else None
                ),
            }
            for submission in submissions_list
        ],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned": len(submissions_list),
        },
        "filters": {
            "language": language or None,
            "question_id": question_id,
        },
    }, 200
