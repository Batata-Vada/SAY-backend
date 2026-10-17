"""Step 7 materialized Codeforces topic and difficulty estimates.

These are derived caches, never sources of official solving evidence.
"""
from datetime import datetime, timezone

from database.db import db


def utc_now():
    return datetime.now(timezone.utc)


class UserTopicMastery(db.Model):
    __tablename__ = "user_topic_mastery"

    uid = db.Column(db.Integer, db.ForeignKey("user.uid"), primary_key=True)
    tag = db.Column(db.String(128), primary_key=True)
    source_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False, index=True
    )
    attempted_problems = db.Column(db.Integer, nullable=False)
    solved_problems = db.Column(db.Integer, nullable=False)
    decided_problems = db.Column(db.Integer, nullable=False)
    rated_decided_problems = db.Column(db.Integer, nullable=False)
    mastery_score = db.Column(db.Float, nullable=True)
    smoothed_success_rate = db.Column(db.Float, nullable=True)
    confidence = db.Column(db.Float, nullable=False)
    mean_rated_difficulty = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        db.CheckConstraint(
            "attempted_problems >= 0 AND solved_problems >= 0 "
            "AND solved_problems <= attempted_problems "
            "AND decided_problems >= 0 AND decided_problems <= attempted_problems "
            "AND rated_decided_problems >= 0 "
            "AND rated_decided_problems <= decided_problems",
            name="ck_user_topic_mastery_counts",
        ),
        db.Index("ix_user_topic_mastery_uid_score", "uid", "mastery_score"),
    )

    def to_dict(self):
        return {
            "tag": self.tag,
            "attempted_problems": self.attempted_problems,
            "solved_problems": self.solved_problems,
            "decided_problems": self.decided_problems,
            "rated_decided_problems": self.rated_decided_problems,
            "mastery_score": self.mastery_score,
            "smoothed_success_rate": self.smoothed_success_rate,
            "confidence": self.confidence,
            "mean_rated_difficulty": self.mean_rated_difficulty,
            "updated_at": self.updated_at.isoformat(),
        }


class UserDifficultyReadiness(db.Model):
    __tablename__ = "user_difficulty_readiness"

    uid = db.Column(db.Integer, db.ForeignKey("user.uid"), primary_key=True)
    source_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False, index=True
    )
    # Lower edge of a 200-point Codeforces problem rating band, not contest rating.
    readiness_rating = db.Column(db.Integer, nullable=True)
    confidence = db.Column(db.Float, nullable=False)
    rated_attempted_problems = db.Column(db.Integer, nullable=False)
    rated_decided_problems = db.Column(db.Integer, nullable=False)
    rated_solved_problems = db.Column(db.Integer, nullable=False)
    rating_bands_raw = db.Column(db.JSON, nullable=False, default=list)
    source_digest = db.Column(db.String(64), nullable=False)
    model_version = db.Column(db.String(32), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        db.CheckConstraint(
            "rated_attempted_problems >= 0 AND rated_decided_problems >= 0 "
            "AND rated_decided_problems <= rated_attempted_problems "
            "AND rated_solved_problems >= 0 "
            "AND rated_solved_problems <= rated_decided_problems",
            name="ck_user_difficulty_readiness_counts",
        ),
    )

    def to_dict(self):
        return {
            "readiness_rating": self.readiness_rating,
            "rating_band_width": 200,
            "confidence": self.confidence,
            "rated_attempted_problems": self.rated_attempted_problems,
            "rated_decided_problems": self.rated_decided_problems,
            "rated_solved_problems": self.rated_solved_problems,
            "rating_bands": self.rating_bands_raw,
            "updated_at": self.updated_at.isoformat(),
            "model_version": self.model_version,
            "interpretation": (
                "Estimated lower edge of a problem difficulty band based on "
                "historical practice; not a Codeforces contest rating."
            ),
        }
