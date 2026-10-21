"""Phase 1 Codeforces recommender with durable, attributable audit logs."""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from uuid import uuid4

from flask import current_app
from sqlalchemy import func

from analytics.difficulty import valid_rating
from analytics.mastery import SkillEstimateError, read_user_skills
from analytics.progress import ProgressBuildError, active_codeforces_account, read_user_progress
from database.db import db
from models.codeforces_submission import CodeforcesSubmission
from models.problem import Problem
from models.recommendation_log import RecommendationLog
from models.user_problem_progress import UserProblemProgress
from models.user_topic_mastery import UserTopicMastery
from models.users import User
from recommendations.candidate_generator import (
    build_history, eligible_candidates, select_rating_window,
)
from recommendations.scoring import MODEL_VERSION, normalized_weights, rank_candidates


class RecommendationError(RuntimeError):
    """Invalid/absent prerequisite; public endpoint should return HTTP 409."""


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _get_profile(uid, account, progress_rows):
    """Return (strategy, target_rating, mastery_map, context_notes)."""
    default_rating = current_app.config.get("RECOMMENDATION_DEFAULT_RATING", 1000)
    if type(default_rating) is not int or not 800 <= default_rating <= 3000:
        raise ValueError("RECOMMENDATION_DEFAULT_RATING must be an integer in 800..3000")
    notes = []
    if account is None:
        notes.append("No linked Codeforces account: cannot exclude solves unknown to SAY.")
        return "cold_start", default_rating, {}, notes
    if not account.ownership_verified:
        notes.append("Codeforces handle ownership is unverified; recommendations describe linked public history.")
    if account.sync_status == "RUNNING":
        raise RecommendationError("Codeforces import is running; retry after it finishes")
    if account.last_synced_at is None:
        notes.append("No completed official history import: use cold-start recommendations until synchronized.")
        return "cold_start", default_rating, {}, notes
    if account.sync_status != "SUCCEEDED":
        raise RecommendationError("Latest Codeforces import did not succeed; retry sync, progress, and skill rebuild")
    try:
        progress_state = read_user_progress(uid, limit=1, offset=0)
    except ProgressBuildError as exc:
        raise RecommendationError(str(exc)) from exc
    if progress_state["needs_rebuild"]:
        raise RecommendationError(f"Progress is stale: flask --app main rebuild-cf-progress --uid {uid}")
    # Even a synced account may have no usable historical problem evidence.
    if not progress_rows:
        notes.append("No resolved individual problem history: cold-start practice range.")
        return "cold_start", default_rating, {}, notes
    try:
        data = read_user_skills(uid, limit=1, offset=0)
    except SkillEstimateError as exc:
        raise RecommendationError(str(exc)) from exc
    readiness = data["difficulty_readiness"]
    account_id = account.id
    topics = db.session.execute(
        db.select(UserTopicMastery).where(
            UserTopicMastery.uid == uid,
            UserTopicMastery.source_account_id == account_id,
        )
    ).scalars().all()
    mastery = {item.tag: {"mastery_score": item.mastery_score, "confidence": item.confidence} for item in topics}
    solved_ratings = db.session.execute(
        db.select(Problem.difficulty_raw).join(
            UserProblemProgress, UserProblemProgress.problem_id == Problem.id
        ).where(
            UserProblemProgress.uid == uid,
            UserProblemProgress.source_account_id == account_id,
            UserProblemProgress.is_solved.is_(True),
            Problem.platform == "CODEFORCES",
        ).order_by(UserProblemProgress.last_submitted_at.desc(), Problem.id)
    ).scalars().all()
    solved_ratings = [r.get("rating") for r in solved_ratings if isinstance(r, dict) and valid_rating(r.get("rating"))]
    recent_level = int(round(median(solved_ratings[:20]) / 100) * 100) if solved_ratings else default_rating
    readiness_level = readiness.get("readiness_rating")
    if readiness_level is not None:
        target = _clamp(readiness_level + 100, 800, 3500)
    else:
        target = _clamp(recent_level + 100, 800, 3500)
    if readiness["rated_decided_problems"] < 12 or readiness["confidence"] < 0.45:
        notes.append("Sparse/low-confidence evidence: use wider candidate windows and exploratory topics.")
        return "sparse", target, mastery, notes
    return "personalized", target, mastery, notes


def _explain(item, profile, target):
    tags = ", ".join(item["tags"][:3]) if item["tags"] else "unclassified topics"
    if item["rating"] is None:
        difficulty = "Unrated fallback; difficulty is not reliably known."
    else:
        difference = item["rating"] - target
        relative = "near" if abs(difference) <= 100 else ("above" if difference > 0 else "below")
        difficulty = f"Rated {item['rating']} ({relative} target {target})."
    if item["candidate_type"] == "retry":
        reason = f"Retry after {item['official_failure_count']} officially failed attempt(s)."
    else:
        reason = "New practice with no recorded individual Codeforces attempt."
    return f"{difficulty} Topics: {tags}; prioritizes weak or uncertain coverage. {reason} Strategy: {profile}."


def generate_recommendations(uid: int, limit: int = 10, mode: str = "new") -> dict:
    if type(uid) is not int or uid < 1:
        raise ValueError("uid must be a positive integer")
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("limit must be an integer in 1..30")
    if mode not in ("new", "retry", "mixed"):
        raise ValueError("mode must be new, retry, or mixed")
    if db.session.get(User, uid) is None:
        raise RecommendationError("SAY user not found")

    weights = normalized_weights(current_app.config.get("RECOMMENDATION_WEIGHTS"))
    cap = current_app.config.get("RECOMMENDATION_CANDIDATE_POOL_CAP", 1200)
    if type(cap) is not int or not 100 <= cap <= 10000:
        raise ValueError("RECOMMENDATION_CANDIDATE_POOL_CAP must be in 100..10000")
    account = active_codeforces_account(uid)
    account_id = account.id if account is not None else None
    progress_rows = []
    submission_rows = []
    if account is not None:
        progress_rows = db.session.execute(db.select(UserProblemProgress).where(
            UserProblemProgress.uid == uid, UserProblemProgress.source_account_id == account.id
        )).scalars().all()
        submission_rows = db.session.execute(db.select(CodeforcesSubmission).where(
            CodeforcesSubmission.codeforces_account_id == account.id
        )).scalars().all()

    profile, target, mastery, notes = _get_profile(uid, account, progress_rows)
    if account is not None:
        by_id, by_external = build_history(progress_rows, submission_rows, account_id=account.id)
    else:
        by_id, by_external = {}, {}
    problems = db.session.execute(db.select(Problem).where(Problem.platform == "CODEFORCES")).scalars().all()
    rated, unrated = eligible_candidates(problems, by_id, by_external, mode=mode)
    required = min(cap, max(limit * 6, 30))
    rating_pool, window = select_rating_window(rated, target=target, required=required, profile=profile)
    rating_pool = rating_pool[:cap]
    now = datetime.now(timezone.utc)
    ranked = rank_candidates(rating_pool, target=target, window=window, mastery=mastery,
                             weights=weights, limit=limit, as_of=now)

    fallback_count = 0
    if len(ranked) < limit:
        # Unrated catalog entries never displace rated candidates.
        unrated.sort(key=lambda x: (x["candidate_type"] != "new", x["external_id"]))
        secondary = rank_candidates(unrated[:cap], target=target, window=window,
                                    mastery=mastery, weights=weights,
                                    limit=limit - len(ranked), as_of=now)
        fallback_count = len(secondary)
        for i, item in enumerate(secondary, len(ranked) + 1):
            item["rank"] = i
        ranked.extend(secondary)
    result = []
    for item in ranked:
        clean = {key: val for key, val in item.items() if key != "last_attempted_at"}
        clean["ranking_strategy"] = "rated" if item["rating"] is not None else "unrated_fallback"
        clean["explanation"] = _explain(item, profile, target)
        result.append(clean)

    run_id = str(uuid4())
    try:
        for item in result:
            db.session.add(RecommendationLog(
                run_id=run_id, uid=uid, source_account_id=account_id,
                problem_id=item["problem_id"], rank=item["rank"],
                request_mode=mode, candidate_type=item["candidate_type"],
                profile_strategy=profile, model_version=MODEL_VERSION,
                target_rating=target, ranking_strategy=item["ranking_strategy"],
                score=item["score"], score_components=item["score_components"],
                scoring_weights=weights, explanation=item["explanation"], created_at=now,
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if not result:
        notes.append("No eligible candidates in the configured safe difficulty windows or unrated fallback.")
    return {
        "run_id": run_id, "model_version": MODEL_VERSION, "uid": uid,
        "codeforces_account_id": account_id,
        "linked_handle": account.handle if account else None,
        "history_sync_status": account.sync_status if account else "NOT_LINKED",
        "mode": mode, "profile": profile, "target_rating": target,
        "rating_window_used": window, "weights": weights,
        "requested": limit, "returned": len(result),
        "candidate_diagnostics": {
            "rated_eligible": len(rated), "unrated_eligible": len(unrated),
            "rated_in_window": len(rating_pool), "unrated_used": fallback_count,
        },
        "notes": notes + ["Codeforces problem accessibility is checked by catalog URL shape, not by live HTTP requests."],
        "recommendations": result,
    }


def recommend_problems(uid: int, limit: int = 10, mode: str = "new") -> list:
    """Return explainable ranked Codeforces problems; persist recommendation logs."""
    return generate_recommendations(uid=uid, limit=limit, mode=mode)["recommendations"]


def read_recommendation_history(uid: int, *, limit: int = 20, offset: int = 0) -> dict:
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("Invalid history pagination")
    query = db.select(RecommendationLog).where(RecommendationLog.uid == uid)
    count = db.session.execute(db.select(func.count()).select_from(RecommendationLog).where(
        RecommendationLog.uid == uid
    )).scalar_one()
    logs = db.session.execute(query.order_by(
        RecommendationLog.created_at.desc(), RecommendationLog.id.desc()
    ).limit(limit).offset(offset)).scalars().all()
    return {"uid": uid, "total": count,
            "pagination": {"limit": limit, "offset": offset, "returned": len(logs)},
            "history": [row.to_dict() for row in logs]}
