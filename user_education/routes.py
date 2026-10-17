from flask import Blueprint, jsonify, request

from middleware.auth import login_required
from database.db import db
from models.user_education import UserEducation


education = Blueprint("education", __name__)


def serialize_education(record):
    return {
        "id": record.id,
        "institution": record.institution,
        "degree": record.degree,
        "field_of_study": record.field_of_study or "",
        "start_year": record.start_year,
        "end_year": record.end_year,
        "is_visible": record.is_visible,
    }


def parse_year(value, field, required=False):
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required.")
        return None

    # An empty end year or "Present" means the education is ongoing.
    if not required and isinstance(value, str):
        if value.strip().lower() == "present":
            return None

    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a valid year.")

    if year < 1900 or year > 2200:
        raise ValueError(f"{field} is outside the accepted year range.")

    return year


@education.route("/me", methods=["GET"])
@login_required
def get_my_education(user):
    records = (
        UserEducation.query
        .filter_by(user_id=user.uid)
        .order_by(UserEducation.start_year.desc(), UserEducation.id.asc())
        .all()
    )

    return jsonify({
        "education": [serialize_education(record) for record in records]
    }), 200


@education.route("/me", methods=["PUT"])
@login_required
def save_my_education(user):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    records_data = data.get("education")

    if not isinstance(records_data, list):
        return jsonify({
            "error": "'education' must be a list."
        }), 400

    is_visible = data.get("is_visible", True)

    if not isinstance(is_visible, bool):
        return jsonify({
            "error": "'is_visible' must be a boolean."
        }), 400

    # Validate the complete payload before changing existing records.
    validated_records = []

    try:
        for index, record in enumerate(records_data):
            if not isinstance(record, dict):
                raise ValueError(
                    f"Education entry {index + 1} must be an object."
                )

            institution = str(record.get("institution") or "").strip()
            degree = str(record.get("degree") or "").strip()
            field_of_study = str(
                record.get("field_of_study") or ""
            ).strip()

            # Ignore a completely blank row from the frontend.
            if not institution and not degree and not field_of_study:
                if not record.get("start_year") and not record.get("end_year"):
                    continue

            if not institution:
                raise ValueError(
                    f"Institution is required for entry {index + 1}."
                )

            if not degree:
                raise ValueError(
                    f"Degree is required for entry {index + 1}."
                )

            if len(institution) > 200:
                raise ValueError(
                    f"Institution is too long in entry {index + 1}."
                )

            if len(degree) > 100:
                raise ValueError(
                    f"Degree is too long in entry {index + 1}."
                )

            if len(field_of_study) > 150:
                raise ValueError(
                    f"Field of study is too long in entry {index + 1}."
                )

            start_year = parse_year(
                record.get("start_year"),
                f"Start year in entry {index + 1}",
                required=True,
            )

            end_year = parse_year(
                record.get("end_year"),
                f"End year in entry {index + 1}",
            )

            if end_year is not None and end_year < start_year:
                raise ValueError(
                    f"End year cannot precede start year "
                    f"in entry {index + 1}."
                )

            validated_records.append({
                "institution": institution,
                "degree": degree,
                "field_of_study": field_of_study or None,
                "start_year": start_year,
                "end_year": end_year,
                "is_visible": is_visible,
            })

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        # Replace this user's education list.
        UserEducation.query.filter_by(user_id=user.uid).delete(
            synchronize_session=False
        )

        for record in validated_records:
            db.session.add(
                UserEducation(
                    user_id=user.uid,
                    **record,
                )
            )

        db.session.commit()

    except Exception:
        db.session.rollback()
        return jsonify({
            "error": "Failed to save education details."
        }), 500

    saved_records = (
        UserEducation.query
        .filter_by(user_id=user.uid)
        .order_by(UserEducation.start_year.desc(), UserEducation.id.asc())
        .all()
    )

    return jsonify({
        "message": "Education details saved successfully.",
        "education": [
            serialize_education(record) for record in saved_records
        ],
    }), 200