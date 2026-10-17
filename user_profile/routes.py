from flask import Blueprint, jsonify, request

from middleware.auth import login_required
from database.db import db
from models.user_profile import UserProfile
from models.users import User
from models.user_education import UserEducation


profile = Blueprint("profile", __name__)

PROFILE_FIELDS = (
    "instagram_url",
    "x_url",
    "linkedin_url",
    "leetcode_url",
    "codeforces_url",
    "codechef_url",
    "show_instagram",
    "show_x",
    "show_linkedin",
    "show_leetcode",
    "show_codeforces",
    "show_codechef",
)


def serialize_profile(user_profile):
    return {
        "id": user_profile.id,
        "instagram_url": user_profile.instagram_url or "",
        "x_url": user_profile.x_url or "",
        "linkedin_url": user_profile.linkedin_url or "",
        "leetcode_url": user_profile.leetcode_url or "",
        "codeforces_url": user_profile.codeforces_url or "",
        "codechef_url": user_profile.codechef_url or "",
        "show_instagram": user_profile.show_instagram,
        "show_x": user_profile.show_x,
        "show_linkedin": user_profile.show_linkedin,
        "show_leetcode": user_profile.show_leetcode,
        "show_codeforces": user_profile.show_codeforces,
        "show_codechef": user_profile.show_codechef,
    }


def get_or_create_profile(user_id):
    user_profile = UserProfile.query.filter_by(user_id=user_id).first()

    if user_profile is None:
        user_profile = UserProfile(user_id=user_id)
        db.session.add(user_profile)
        db.session.flush()

    return user_profile


@profile.route("/me", methods=["GET"])
@login_required
def get_my_profile(user):
    user_profile = get_or_create_profile(user.uid)
    db.session.commit()

    return jsonify({
        "profile": serialize_profile(user_profile)
    }), 200


@profile.route("/me", methods=["PUT"])
@login_required
def save_my_profile(user):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    user_profile = get_or_create_profile(user.uid)

    for field in PROFILE_FIELDS:
        if field not in data:
            continue

        value = data[field]

        if field.startswith("show_"):
            if not isinstance(value, bool):
                return jsonify({
                    "error": f"{field} must be a boolean."
                }), 400
        else:
            if value is not None and not isinstance(value, str):
                return jsonify({
                    "error": f"{field} must be a string."
                }), 400

            value = (value or "").strip() or None

        setattr(user_profile, field, value)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save profile."}), 500

    return jsonify({
        "message": "Profile saved successfully.",
        "profile": serialize_profile(user_profile),
    }), 200

@profile.route("/<string:username>", methods=["GET"])
def get_public_profile(username):
    user = User.query.filter_by(name=username).first()

    if user is None:
        return jsonify({"error": "User not found."}), 404

    user_profile = UserProfile.query.filter_by(user_id=user.uid).first()

    response = {
        "uid": user.uid,
        "username": user.name,
        "name": user.name,
        "bio": user_profile.bio or "" if user_profile else "",
        "education": [],
        "instagram_url": "",
        "x_url": "",
        "linkedin_url": "",
        "leetcode_url": "",
        "codeforces_url": "",
        "codechef_url": "",
        "show_instagram": False,
        "show_x": False,
        "show_linkedin": False,
        "show_leetcode": False,
        "show_codeforces": False,
        "show_codechef": False,
    }

    # Fetch publicly visible education records
    education_records = UserEducation.query.filter_by(
        user_id=user.uid,
        is_visible=True,
    ).all()

    response["education"] = [
        {
            "institution": education.institution,
            "degree": education.degree,
            "field_of_study": education.field_of_study,
            "start_year": education.start_year,
            "end_year": education.end_year,
        }
        for education in education_records
    ]

    # Fetch social links, respecting visibility settings
    if user_profile:
        social_fields = {
            "instagram_url": "show_instagram",
            "x_url": "show_x",
            "linkedin_url": "show_linkedin",
            "leetcode_url": "show_leetcode",
            "codeforces_url": "show_codeforces",
            "codechef_url": "show_codechef",
        }

        for url_field, visibility_field in social_fields.items():
            is_visible = bool(
                getattr(user_profile, visibility_field, False)
            )

            response[visibility_field] = is_visible

            if is_visible:
                response[url_field] = (
                    getattr(user_profile, url_field, None) or ""
                )

    return jsonify(response), 200