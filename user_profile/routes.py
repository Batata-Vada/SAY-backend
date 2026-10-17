from flask import Blueprint, request
from sqlalchemy.exc import SQLAlchemyError

from database.db import db
from middleware.auth import login_required
from models.user_profile import UserProfile

user_profile = Blueprint("user_profile", __name__)

PROFILE_FIELDS = (
    "instagram_url", "x_url", "linkedin_url",
    "leetcode_url", "codeforces_url", "codechef_url",
    "show_instagram", "show_x", "show_linkedin",
    "show_leetcode", "show_codeforces", "show_codechef",
)


def serialize_profile(profile):
    return {field: getattr(profile, field) for field in PROFILE_FIELDS}


@user_profile.route("/profile/me", methods=["GET"])
@login_required
def get_my_profile(user):
    profile = UserProfile.query.filter_by(uid=user.uid).first()
    return {"profile": serialize_profile(profile) if profile else None}, 200


@user_profile.route("/profile/me", methods=["PUT"])
@login_required
def save_my_profile(user):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"message": "A JSON object is required"}, 400

    unknown = set(data) - set(PROFILE_FIELDS)
    if unknown:
        return {"message": "Unknown fields", "fields": sorted(unknown)}, 400

    profile = UserProfile.query.filter_by(uid=user.uid).first()
    if profile is None:
        profile = UserProfile(uid=user.uid)
        db.session.add(profile)

    for field, value in data.items():
        if field.startswith("show_"):
            if not isinstance(value, bool):
                return {"message": f"{field} must be a boolean"}, 400
        elif value is not None and (
            not isinstance(value, str) or len(value) > 500
        ):
            return {"message": f"{field} must be a string of at most 500 characters"}, 400
        setattr(profile, field, value)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Could not save profile"}, 500

    return {"message": "Profile saved successfully", "profile": serialize_profile(profile)}, 200
