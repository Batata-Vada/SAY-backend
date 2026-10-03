from datetime import datetime, timezone

from database.db import db


class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)

    platform = db.Column(
        db.String(32),
        nullable=False,
        index=True,
    )

    external_id = db.Column(
        db.String(128),
        nullable=False,
    )

    title = db.Column(
        db.String(512),
        nullable=False,
    )

    slug = db.Column(
        db.String(512),
        nullable=True,
    )

    url = db.Column(
        db.String(1024),
        nullable=False,
    )

    contest_id = db.Column(
        db.String(128),
        nullable=True,
    )

    problem_index = db.Column(
        db.String(64),
        nullable=True,
    )

    category = db.Column(
        db.String(255),
        nullable=True,
    )

    #
    # Keep platform-specific data raw for now.
    #
    difficulty_raw = db.Column(
        db.JSON,
        nullable=True,
    )

    tags_raw = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    stats_raw = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    metadata_raw = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    last_fetched_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "platform",
            "external_id",
            name="uq_problem_platform_external_id",
        ),
    )

    def __repr__(self):
        return (
            f"<Problem "
            f"{self.platform}:{self.external_id} "
            f"{self.title}>"
        )