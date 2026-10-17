"""A SAY user's association with a public Codeforces account."""

from datetime import datetime, timezone

from sqlalchemy import Index, text

from database.db import db


def utc_now():
    return datetime.now(timezone.utc)


class CodeforcesAccount(db.Model):
    __tablename__ = "codeforces_accounts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid"),
        nullable=False,
        index=True
    )

    handle = db.Column(
        db.String(64),
        nullable=False
    )

    ownership_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    linked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    unlinked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    last_synced_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    sync_status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING"
    )

    last_sync_error = db.Column(
        db.String(255),
        nullable=True
    )

    registration_time_seconds = db.Column(
        db.Integer,
        nullable=True
    )

    __table_args__ = (
        Index(
            "uq_codeforces_one_active_link_per_user",
            "uid",
            unique=True,
            sqlite_where=text("unlinked_at IS NULL"),
            postgresql_where=text("unlinked_at IS NULL"),
        ),
    )

    def to_dict(self):
        def timestamp(value):
            return value.isoformat() if value else None

        return {
            "id": self.id,
            "handle": self.handle,
            "ownership_verified": self.ownership_verified,
            "linked_at": timestamp(self.linked_at),
            "last_synced_at": timestamp(self.last_synced_at),
            "sync_status": self.sync_status,
            "last_sync_error": self.last_sync_error,
        }