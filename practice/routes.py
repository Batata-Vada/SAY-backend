from datetime import datetime, timezone

from flask import Blueprint, request

from analytics.progress import active_codeforces_account
from database.db import db
from middleware.auth import login_required
from models.practice_session import PracticeSession
from models.problem import Problem
from recommendations.feature_history import official_solved_in_session
from models.recommendation_log import RecommendationLog
from uuid import UUID

practice = Blueprint("practice", __name__, url_prefix="/api/me/practice-sessions")


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@practice.get("")
@login_required
def list_sessions(user):
    account = active_codeforces_account(user.uid)
    if account is None:
        return {"sessions": []}, 200
    query = db.select(PracticeSession).where(
        PracticeSession.uid == user.uid,
        PracticeSession.source_account_id == account.id,
    )
    raw_id = request.args.get("problem_id")
    if raw_id is not None:
        try:
            problem_id = int(raw_id)
        except (TypeError, ValueError):
            return {"message": "Invalid problem_id"}, 400
        if problem_id < 1:
            return {"message": "Invalid problem_id"}, 400
        query = query.where(PracticeSession.problem_id == problem_id)
    rows = db.session.execute(
        query.order_by(PracticeSession.started_at.desc(), PracticeSession.id.desc()).limit(30)
    ).scalars().all()
    return {"sessions": [row.to_dict(official_solved_in_session(row)) for row in rows]}, 200, {
        "Cache-Control": "private, no-store"
    }


@practice.post("")
@login_required
def start_session(user):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get("problem_id")) is not int:
        return {"message": "A numeric problem_id is required"}, 400
    account = active_codeforces_account(user.uid)
    if account is None or not account.ownership_verified:
        return {"message": "A verified Codeforces account is required"}, 409
    problem = db.session.get(Problem, data["problem_id"])
    if problem is None or problem.platform != "CODEFORCES":
        return {"message": "Codeforces problem not found"}, 404
    running = db.session.execute(db.select(PracticeSession).where(
        PracticeSession.uid == user.uid, PracticeSession.status == "ACTIVE"
    ).order_by(PracticeSession.id.desc()).limit(1)).scalar_one_or_none()
    if running is not None:
        if (datetime.now(timezone.utc) - _utc(running.started_at)).total_seconds() <= 14400:
            return {"message": "Finish your current practice session first",
                    "session": running.to_dict()}, 409
        running.status = "ABANDONED"
        running.finished_at = datetime.now(timezone.utc)
    run_id = data.get("recommendation_run_id")
    if run_id is not None:
        if not isinstance(run_id, str) or len(run_id) != 36:
            return {"message": "Invalid recommendation_run_id"}, 400
        try:
            parsed = UUID(run_id)
        except (ValueError, AttributeError):
            return {"message": "Invalid recommendation_run_id"}, 400
        if str(parsed) != run_id:
            return {"message": "Invalid recommendation_run_id"}, 400
        matching = db.session.execute(
            db.select(RecommendationLog.id).where(
                RecommendationLog.run_id == run_id,
                RecommendationLog.uid == user.uid,
                RecommendationLog.problem_id == problem.id,
            ).limit(1)
        ).first()
        if matching is None:
            return {"message": "Recommendation not found for this problem"}, 409
    row = PracticeSession(uid=user.uid, source_account_id=account.id,
                          problem_id=problem.id, status="ACTIVE",
                          started_at=datetime.now(timezone.utc),
                          recommendation_run_id=run_id)
    db.session.add(row)
    db.session.commit()
    return {"session": row.to_dict()}, 201, {"Cache-Control": "no-store"}


@practice.post("/<int:session_id>/finish")
@login_required
def finish_session(user, session_id):
    row = db.session.get(PracticeSession, session_id)
    account = active_codeforces_account(user.uid)
    if row is None or row.uid != user.uid or account is None or row.source_account_id != account.id:
        return {"message": "Session not found"}, 404
    if row.status != "ACTIVE":
        return {"message": "Session has already ended"}, 409
    finished = datetime.now(timezone.utc)
    elapsed = int((finished - _utc(row.started_at)).total_seconds())
    if elapsed < 60:
        return {"message": "Practice duration must be at least one minute"}, 409
    if elapsed > 14400:
        row.status = "ABANDONED"
        row.finished_at = finished
        db.session.commit()
        return {"message": "Session exceeded the four-hour limit"}, 409
    row.status = "FINISHED"
    row.finished_at = finished
    row.duration_seconds = elapsed
    db.session.commit()
    verified = official_solved_in_session(row)
    return {"session": row.to_dict(verified),
            "message": "Session recorded. An official Codeforces accepted submission is required for model training."}, 200, {
        "Cache-Control": "no-store"
    }
