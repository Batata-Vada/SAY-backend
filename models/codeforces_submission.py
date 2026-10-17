"""Official public Codeforces submissions, separate from SAY source-file submissions."""
from datetime import datetime, timezone
from database.db import db


def utc_now():
    return datetime.now(timezone.utc)


class CodeforcesSubmission(db.Model):
    __tablename__ = "codeforces_submissions"

    id = db.Column(db.Integer, primary_key=True)
    codeforces_account_id = db.Column(
        db.Integer, db.ForeignKey("codeforces_accounts.id"), nullable=False, index=True
    )
    cf_submission_id = db.Column(db.BigInteger, nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=True, index=True)

    # Keep the problem identity even when our catalog cannot resolve it yet.
    cf_contest_id = db.Column(db.String(128), nullable=True)
    cf_problem_index = db.Column(db.String(64), nullable=True)
    cf_problemset_name = db.Column(db.String(128), nullable=True)
    cf_problem_name = db.Column(db.String(512), nullable=True)
    cf_problem_external_id = db.Column(db.String(128), nullable=True)

    verdict = db.Column(db.String(64), nullable=True)
    testset = db.Column(db.String(64), nullable=True)
    programming_language = db.Column(db.String(128), nullable=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    time_consumed_ms = db.Column(db.Integer, nullable=True)
    memory_consumed_bytes = db.Column(db.BigInteger, nullable=True)
    passed_test_count = db.Column(db.Integer, nullable=True)
    participant_type = db.Column(db.String(64), nullable=True)

    # TEAM/UNKNOWN/UNCERTAIN submissions must not become individual mastery evidence.
    attribution_status = db.Column(db.String(16), nullable=False)
    author_members_raw = db.Column(db.JSON, nullable=False, default=list)
    raw_problem = db.Column(db.JSON, nullable=False, default=dict)
    last_checked_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "codeforces_account_id", "cf_submission_id",
            name="uq_cf_submission_account_official_id",
        ),
        db.Index("ix_cf_submissions_account_submitted", "codeforces_account_id", "submitted_at"),
    )

    @property
    def is_final_individual_solve(self):
        return (
            self.verdict == "OK"
            and self.testset == "TESTS"
            and self.attribution_status == "INDIVIDUAL"
        )