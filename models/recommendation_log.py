"""Append-only audit trail for SAY's recommendation experiments."""
from datetime import datetime, timezone
from database.db import db


class RecommendationLog(db.Model):
    __tablename__ = "recommendation_logs"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(36), nullable=False, index=True)
    uid = db.Column(db.Integer, db.ForeignKey("user.uid"), nullable=False, index=True)
    source_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=True
    )
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    request_mode = db.Column(db.String(16), nullable=False)
    candidate_type = db.Column(db.String(16), nullable=False)
    profile_strategy = db.Column(db.String(24), nullable=False)
    model_version = db.Column(db.String(32), nullable=False)
    target_rating = db.Column(db.Integer, nullable=False)
    ranking_strategy = db.Column(db.String(16), nullable=False)
    score = db.Column(db.Float, nullable=False)
    score_components = db.Column(db.JSON, nullable=False)
    scoring_weights = db.Column(db.JSON, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index("ix_recommendation_logs_uid_created", "uid", "created_at"),
        db.UniqueConstraint("run_id", "rank", name="uq_recommendation_run_rank"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "problem_id": self.problem_id,
            "rank": self.rank,
            "request_mode": self.request_mode,
            "candidate_type": self.candidate_type,
            "profile_strategy": self.profile_strategy,
            "model_version": self.model_version,
            "target_rating": self.target_rating,
            "ranking_strategy": self.ranking_strategy,
            "score": self.score,
            "score_components": self.score_components,
            "scoring_weights": self.scoring_weights,
            "explanation": self.explanation,
            "created_at": self.created_at.isoformat(),
        }
