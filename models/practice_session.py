from datetime import datetime, timezone
from database.db import db


class PracticeSession(db.Model):
    __tablename__ = "practice_sessions"

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.Integer, db.ForeignKey("user.uid"), nullable=False, index=True)
    source_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False, index=True
    )
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="ACTIVE")
    started_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.Index("ix_practice_user_status", "uid", "status"),
        db.CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0",
                           name="ck_practice_duration_positive"),
    )

    def to_dict(self, verified=False):
        return {
            "id": self.id,
            "problem_id": self.problem_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "official_solve_verified": bool(verified),
        }
