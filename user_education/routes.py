from flask import Blueprint, request
from sqlalchemy.exc import SQLAlchemyError

from database.db import db
from middleware.auth import login_required
from models.user_education import UserEducation

user_education = Blueprint("user_education", __name__)


def serialize_education(entry):
    return {
        "id": entry.id,
        "institution": entry.institution,
        "degree": entry.degree,
        "field_of_study": entry.field_of_study,
        "start_year": entry.start_year,
        "end_year": entry.end_year,
        "is_visible": entry.is_visible,
    }


def validate_payload(data):
    if not isinstance(data, dict):
        return "A JSON object is required"
    for field in ("institution", "degree"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"{field} is required"
    for field, max_length in (
        ("institution", 200), ("degree", 120),
        ("field_of_study", 160), ("start_year", 20), ("end_year", 20),
    ):
        value = data.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > max_length):
            return f"Invalid {field}"
    if "is_visible" in data and not isinstance(data["is_visible"], bool):
        return "is_visible must be a boolean"
    return None


@user_education.route("/education/me", methods=["GET"])
@login_required
def get_my_education(user):
    entries = UserEducation.query.filter_by(uid=user.uid).order_by(UserEducation.id.asc()).all()
    return {"education": [serialize_education(entry) for entry in entries]}, 200


@user_education.route("/education/me", methods=["POST"])
@login_required
def create_education(user):
    data = request.get_json(silent=True)
    error = validate_payload(data)
    if error:
        return {"message": error}, 400

    entry = UserEducation(
        uid=user.uid,
        institution=data["institution"].strip(),
        degree=data["degree"].strip(),
        field_of_study=data.get("field_of_study"),
        start_year=data.get("start_year"),
        end_year=data.get("end_year"),
        is_visible=data.get("is_visible", True),
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Could not create education record"}, 500
    return {"message": "Education created successfully", "education": serialize_education(entry)}, 201


@user_education.route("/education/me/<int:education_id>", methods=["PUT"])
@login_required
def update_education(user, education_id):
    entry = UserEducation.query.filter_by(id=education_id, uid=user.uid).first()
    if entry is None:
        return {"message": "Education record not found"}, 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"message": "A JSON object is required"}, 400
    allowed = {"institution", "degree", "field_of_study", "start_year", "end_year", "is_visible"}
    if set(data) - allowed:
        return {"message": "Unknown fields", "fields": sorted(set(data) - allowed)}, 400
    merged = {
        "institution": data.get("institution", entry.institution),
        "degree": data.get("degree", entry.degree),
        "field_of_study": data.get("field_of_study", entry.field_of_study),
        "start_year": data.get("start_year", entry.start_year),
        "end_year": data.get("end_year", entry.end_year),
        "is_visible": data.get("is_visible", entry.is_visible),
    }
    error = validate_payload(merged)
    if error:
        return {"message": error}, 400
    for field, value in merged.items():
        setattr(entry, field, value.strip() if field in ("institution", "degree") else value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Could not update education record"}, 500
    return {"message": "Education updated successfully", "education": serialize_education(entry)}, 200


@user_education.route("/education/me/<int:education_id>", methods=["DELETE"])
@login_required
def delete_education(user, education_id):
    entry = UserEducation.query.filter_by(id=education_id, uid=user.uid).first()
    if entry is None:
        return {"message": "Education record not found"}, 404
    try:
        db.session.delete(entry)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"message": "Could not delete education record"}, 500
    return {"message": "Education deleted successfully"}, 200
