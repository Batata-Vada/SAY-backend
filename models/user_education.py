from datetime import datetime, timezone

from database.db import db


def utc_now_for_legacy_column():
    """Store naive UTC to match the existing SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserEducation(db.Model):
    __tablename__ = "user_education"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.uid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    institution = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(100), nullable=False)
    field_of_study = db.Column(db.String(150), nullable=True)

    start_year = db.Column(db.Integer, nullable=False)
    end_year = db.Column(db.Integer, nullable=True)

    is_visible = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_for_legacy_column,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_for_legacy_column,
        onupdate=utc_now_for_legacy_column,
    )
