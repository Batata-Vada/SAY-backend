# backend/models/submission.py

from datetime import datetime, timezone

from database.db import db


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid"),
        nullable=False,
        index=True
    )

    question_id = db.Column(
        db.Integer,
        nullable=False,
        index=True
    )

    language = db.Column(
        db.String(10),
        nullable=False
    )

    filename = db.Column(
        db.String(255),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        db.CheckConstraint(
            "language IN ('python', 'cpp')",
            name="check_submission_language"
        ),
        db.UniqueConstraint(
            "uid",
            "question_id",
            "filename",
            name="uq_submission_filename"
        )
    )