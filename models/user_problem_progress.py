"""Rebuildable, per-SAY-user progress derived only from official Codeforces data."""

from database.db import db


class UserProblemProgress(db.Model):
    __tablename__ = "user_problem_progress"

    # Exactly one row per SAY user and canonical Codeforces problem.
    uid = db.Column(
        db.Integer, db.ForeignKey("user.uid"), primary_key=True
    )
    problem_id = db.Column(
        db.Integer, db.ForeignKey("problems.id"), primary_key=True
    )
    # Guards against accidentally serving a prior user's linked CF history.
    source_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False,
        index=True,
    )

    official_submission_count = db.Column(db.Integer, nullable=False)
    official_failure_count = db.Column(db.Integer, nullable=False)
    official_final_ok_count = db.Column(db.Integer, nullable=False)
    official_pending_count = db.Column(db.Integer, nullable=False)
    official_provisional_ok_count = db.Column(db.Integer, nullable=False)
    official_unclassified_count = db.Column(db.Integer, nullable=False)
    is_solved = db.Column(db.Boolean, nullable=False)

    first_attempted_at = db.Column(db.DateTime(timezone=True), nullable=False)
    first_solved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_submitted_at = db.Column(db.DateTime(timezone=True), nullable=False)
    # Deterministic: the latest last_checked_at of the contributing evidence.
    progress_updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        db.Index("ix_user_problem_progress_uid_solved", "uid", "is_solved"),
        db.CheckConstraint(
            "official_submission_count >= 1 AND official_failure_count >= 0 "
            "AND official_final_ok_count >= 0 AND official_pending_count >= 0 "
            "AND official_provisional_ok_count >= 0 AND official_unclassified_count >= 0",
            name="ck_user_problem_progress_nonnegative",
        ),
    )

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    def to_dict(self, problem):
        return {
            "problem_id": self.problem_id,
            "external_id": problem.external_id,
            "title": problem.title,
            "url": problem.url,
            "rating": problem.codeforces_rating,
            "tags": problem.tags_raw or [],
            "official_submission_count": self.official_submission_count,
            "official_failure_count": self.official_failure_count,
            "official_final_ok_count": self.official_final_ok_count,
            "official_pending_count": self.official_pending_count,
            "official_provisional_ok_count": self.official_provisional_ok_count,
            "official_unclassified_count": self.official_unclassified_count,
            "is_solved": self.is_solved,
            "first_attempted_at": self._iso(self.first_attempted_at),
            "first_solved_at": self._iso(self.first_solved_at),
            "last_submitted_at": self._iso(self.last_submitted_at),
            "progress_updated_at": self._iso(self.progress_updated_at),
        }
