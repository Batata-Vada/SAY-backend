"""Durable requests for refreshing a linked Codeforces account's official history.

A queue row survives HTTP worker restarts; execution is done by a separate CLI
worker, never by an HTTP request. Each user can have at most one open job for
an active linked Codeforces account.
"""
from datetime import datetime, timezone
from sqlalchemy import Index, text
from database.db import db


def utc_now():
    return datetime.now(timezone.utc)


class CodeforcesSyncRequest(db.Model):
    __tablename__ = "codeforces_sync_requests"

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.Integer, db.ForeignKey("user.uid"), nullable=False, index=True)
    codeforces_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False, index=True
    )
    full = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(16), nullable=False, default="QUEUED")
    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    result_raw = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_cf_sync_requests_status",
        ),
        Index(
            "uq_cf_sync_requests_open_account", "codeforces_account_id", unique=True,
            sqlite_where=text("status IN ('QUEUED','RUNNING')"),
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
        db.Index("ix_cf_sync_requests_account_requested", "codeforces_account_id", "requested_at"),
    )

    def to_dict(self):
        def iso(dt):
            return dt.isoformat() if dt is not None else None
        return {
            "id": self.id,
            "status": self.status,
            "full": self.full,
            "requested_at": iso(self.requested_at),
            "started_at": iso(self.started_at),
            "finished_at": iso(self.finished_at),
            "result": self.result_raw,
            "error": self.error_message,
        }
