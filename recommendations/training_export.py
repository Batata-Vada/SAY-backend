"""Authenticated, paginated export of verified Codeforces practice outcomes."""
import hashlib
import hmac
from datetime import datetime, timezone

from flask import Blueprint, current_app, request

from database.db import db
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from models.practice_session import PracticeSession
from models.problem import Problem
from recommendations.feature_history import (
    FEATURE_CONTRACT, MIN_TRAINING_TIMED_SOLVES, collect_timed_solve_profile,
)

training_export = Blueprint(
    "training_export", __name__, url_prefix="/api/internal/project-red"
)

_FINAL_FAILURE_VERDICTS = frozenset({
    "FAILED", "WRONG_ANSWER", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED",
    "RUNTIME_ERROR", "COMPILATION_ERROR", "PRESENTATION_ERROR",
    "IDLENESS_LIMIT_EXCEEDED", "SECURITY_VIOLATED", "CRASHED",
    "INPUT_PREPARATION_CRASHED", "CHALLENGED",
})


def authorized():
    expected = current_app.config.get("PROJECT_RED_EXPORT_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not supplied.startswith("Bearer "):
        return False
    return hmac.compare_digest(supplied[len("Bearer "):], expected)


def timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def user_key(uid, account_id, secret):
    message = f"{uid}:{account_id}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def submission_exists(*conditions):
    return db.select(CodeforcesSubmission.id).where(
        CodeforcesSubmission.codeforces_account_id == PracticeSession.source_account_id,
        CodeforcesSubmission.problem_id == PracticeSession.problem_id,
        CodeforcesSubmission.attribution_status == "INDIVIDUAL",
        *conditions,
    ).exists()


@training_export.get("/events")
def export_events():
    if not authorized():
        return {"message": "Unauthorized"}, 401
    secret = current_app.config.get("PROJECT_RED_PSEUDONYM_KEY", "")
    if not secret:
        return {"message": "Export not configured"}, 503
    try:
        after_id = int(request.args.get("after_id", 0))
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        return {"message": "Invalid pagination"}, 400
    if after_id < 0 or not 1 <= limit <= 500:
        return {"message": "Invalid pagination"}, 400

    during = (
        CodeforcesSubmission.submitted_at >= PracticeSession.started_at,
        CodeforcesSubmission.submitted_at <= PracticeSession.finished_at,
    )
    solved = submission_exists(
        *during,
        CodeforcesSubmission.verdict == "OK",
        CodeforcesSubmission.testset == "TESTS",
    )
    attempted = submission_exists(*during)
    definitive_failure = submission_exists(
        *during,
        CodeforcesSubmission.verdict.in_(_FINAL_FAILURE_VERDICTS),
        CodeforcesSubmission.final_verdict_observed_at.is_not(None),
    )
    unresolved = submission_exists(
        *during,
        db.or_(
            CodeforcesSubmission.verdict.is_(None),
            CodeforcesSubmission.verdict.in_(("TESTING", "SKIPPED")),
            db.and_(
                CodeforcesSubmission.verdict == "OK",
                CodeforcesSubmission.testset != "TESTS",
            ),
            CodeforcesSubmission.final_verdict_observed_at.is_(None),
        ),
    )
    previously_solved = submission_exists(
        CodeforcesSubmission.submitted_at < PracticeSession.started_at,
        CodeforcesSubmission.verdict == "OK",
        CodeforcesSubmission.testset == "TESTS",
    )
    query = (
        db.select(
            PracticeSession, Problem, CodeforcesAccount,
            solved.label("solved"),
            attempted.label("attempted"),
            definitive_failure.label("failure"),
            unresolved.label("unresolved"),
            previously_solved.label("previously_solved"),
        )
        .join(Problem, PracticeSession.problem_id == Problem.id)
        .join(CodeforcesAccount, PracticeSession.source_account_id == CodeforcesAccount.id)
        .where(
            PracticeSession.id > after_id,
            PracticeSession.uid == CodeforcesAccount.uid,
            PracticeSession.status == "FINISHED",
            PracticeSession.finished_at.is_not(None),
            PracticeSession.duration_seconds.between(60, 14400),
            Problem.platform == "CODEFORCES",
            CodeforcesAccount.ownership_verified.is_(True),
            CodeforcesAccount.unlinked_at.is_(None),
            CodeforcesAccount.sync_status == "SUCCEEDED",
            CodeforcesAccount.last_synced_at.is_not(None),
            CodeforcesAccount.last_synced_at >= PracticeSession.finished_at,
        )
        .order_by(PracticeSession.id.asc())
        .limit(limit + 1)
    )
    all_rows = db.session.execute(query).all()
    has_more = len(all_rows) > limit
    rows = all_rows[:limit]
    events = []
    for session, problem, account, ok, attempt, failure, pending, prior in rows:
        rating = problem.codeforces_rating
        if type(rating) is not int or not 800 <= rating <= 3500:
            rating = None
        full_coverage = (
            account.last_full_sync_at is not None
            and account.last_full_sync_at >= session.finished_at
        )
        if ok:
            outcome = "SOLVED"
        elif failure and not pending and full_coverage:
            outcome = "FAILED"
        else:
            outcome = "UNKNOWN"
        history = collect_timed_solve_profile(
            session.uid, account, as_of=session.started_at,
            minimum=MIN_TRAINING_TIMED_SOLVES,
        )
        tags = problem.tags_raw if isinstance(problem.tags_raw, list) else []
        events.append({
            "event_id": session.id,
            "user_key": user_key(session.uid, account.id, secret),
            "problem_external_id": problem.external_id,
            "problem_rating": rating,
            "tags": [tag for tag in tags if isinstance(tag, str)],
            "started_at": timestamp(session.started_at),
            "finished_at": timestamp(session.finished_at),
            "duration_seconds": session.duration_seconds,
            "official_solved": bool(ok),
            "official_attempt_observed": bool(attempt),
            "final_failure_observed": bool(failure),
            "previously_solved": bool(prior),
            "full_history_coverage": bool(full_coverage),
            "outcome_status": outcome,
            "history_features": history,
            "recommendation_run_id": session.recommendation_run_id,
        })
    next_id = rows[-1][0].id if has_more and rows else None
    return {
        "schema_version": 2,
        "feature_contract": FEATURE_CONTRACT,
        "exported_at": timestamp(datetime.now(timezone.utc)),
        "events": events,
        "next_after_id": next_id,
    }, 200, {"Cache-Control": "private, no-store"}
