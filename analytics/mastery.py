"""Derive and serve user topic mastery from materialized Codeforces progress.

No local saved-code submissions and no Codeforces contest rating are used.
Skills are estimates with uncertainty, not proven mastery.
"""

from datetime import datetime, timezone
import hashlib
import json

from database.db import db
from analytics.mastery_math import derive_topic_mastery
from analytics.aggregation import as_utc
from analytics.progress import active_codeforces_account, read_user_progress
from analytics.difficulty import (
    MODEL_VERSION, ProblemEvidence, estimate_difficulty_readiness, valid_rating,
)
from models.problem import Problem
from models.user_problem_progress import UserProblemProgress
from models.user_topic_mastery import UserTopicMastery, UserDifficultyReadiness
from models.users import User


class SkillEstimateError(RuntimeError):
    """Skills are unavailable or stale; source needs review/rebuilding."""


def _normalized_tags(raw):
    if not isinstance(raw, list):
        return ()
    return tuple(sorted({x.strip().lower() for x in raw if isinstance(x, str) and x.strip()}))


def _source_evidence(uid, account_id):
    result = db.session.execute(
        db.select(UserProblemProgress, Problem)
        .join(Problem, UserProblemProgress.problem_id == Problem.id)
        .where(
            UserProblemProgress.uid == uid,
            UserProblemProgress.source_account_id == account_id,
            Problem.platform == "CODEFORCES",
        ).order_by(UserProblemProgress.problem_id)
    ).all()
    evidence = []
    digest_rows = []
    for progress, problem in result:
        rating = problem.codeforces_rating
        if not valid_rating(rating):
            rating = None
        tags = _normalized_tags(problem.tags_raw)
        evidence.append(ProblemEvidence(
            problem_id=progress.problem_id,
            tags=tags,
            rating=rating,
            is_solved=bool(progress.is_solved),
            official_failure_count=progress.official_failure_count,
            last_submitted_at=as_utc(progress.last_submitted_at),
        ))
        digest_rows.append((
            progress.problem_id,
            rating,
            tags,
            bool(progress.is_solved),
            progress.official_failure_count,
            progress.official_submission_count,
            as_utc(progress.last_submitted_at).isoformat(),
            as_utc(progress.progress_updated_at).isoformat(),
        ))
    encoded = json.dumps(digest_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return evidence, hashlib.sha256(encoded).hexdigest()


def _check_progress(uid, account):
    if account.sync_status == "RUNNING":
        raise SkillEstimateError("Submission synchronization is running; retry afterward")
    if account.last_synced_at is None:
        raise SkillEstimateError("Import official Codeforces submissions before estimating skills")
    # Step 6 has its own snapshot consistency check against official evidence.
    prior = read_user_progress(uid, limit=1, offset=0)
    if prior["needs_rebuild"]:
        raise SkillEstimateError(
            "Progress is outdated; run flask --app main rebuild-cf-progress --uid " + str(uid)
        )


def rebuild_user_skills(uid: int, *, as_of: datetime | None = None) -> dict:
    """Replace topic rows and readiness row in one SQL transaction."""
    if type(uid) is not int or uid < 1:
        raise ValueError("uid must be a positive SAY User.uid")
    if db.session.get(User, uid) is None:
        raise SkillEstimateError("SAY user not found")
    account = active_codeforces_account(uid)
    if account is None:
        raise SkillEstimateError("No active Codeforces account linked")
    _check_progress(uid, account)
    as_of = as_utc(as_of or datetime.now(timezone.utc))
    evidence, source_digest = _source_evidence(uid, account.id)
    topic_rows = derive_topic_mastery(evidence, as_of=as_of)
    readiness = estimate_difficulty_readiness(evidence, as_of=as_of)

    try:
        db.session.execute(db.delete(UserTopicMastery).where(UserTopicMastery.uid == uid))
        for row in topic_rows:
            db.session.add(UserTopicMastery(
                uid=uid, source_account_id=account.id, updated_at=as_of, **row
            ))
        summary = db.session.get(UserDifficultyReadiness, uid)
        if summary is None:
            summary = UserDifficultyReadiness(uid=uid)
            db.session.add(summary)
        summary.source_account_id = account.id
        summary.readiness_rating = readiness["readiness_rating"]
        summary.confidence = readiness["confidence"]
        summary.rated_attempted_problems = readiness["rated_attempted_problems"]
        summary.rated_decided_problems = readiness["rated_decided_problems"]
        summary.rated_solved_problems = readiness["rated_solved_problems"]
        summary.rating_bands_raw = readiness["rating_bands"]
        summary.source_digest = source_digest
        summary.model_version = MODEL_VERSION
        summary.updated_at = as_of
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "uid": uid,
        "codeforces_account_id": account.id,
        "handle": account.handle,
        "topics_with_exposure": len(topic_rows),
        "topics_with_estimates": sum(r["mastery_score"] is not None for r in topic_rows),
        "readiness_rating": readiness["readiness_rating"],
        "confidence": readiness["confidence"],
        "rated_decided_problems": readiness["rated_decided_problems"],
        "updated_at": as_of.isoformat(),
        "model_version": MODEL_VERSION,
    }


def read_user_skills(uid: int, *, limit: int = 100, offset: int = 0) -> dict:
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("limit must be 1..100 and offset >= 0")
    account = active_codeforces_account(uid)
    if account is None:
        raise SkillEstimateError("No active Codeforces account linked")
    _check_progress(uid, account)
    summary = db.session.get(UserDifficultyReadiness, uid)
    if summary is None or summary.source_account_id != account.id or summary.model_version != MODEL_VERSION:
        raise SkillEstimateError(
            "Skill estimates have not been built for the active account; "
            "run flask --app main rebuild-cf-skills --uid " + str(uid)
        )
    # Exact digest of the materialized evidence AND problem tags / ratings.
    _, source_digest = _source_evidence(uid, account.id)
    if summary.source_digest != source_digest:
        raise SkillEstimateError(
            "Skill estimates are stale; run flask --app main rebuild-cf-skills --uid " + str(uid)
        )
    if as_utc(account.last_synced_at) > as_utc(summary.updated_at):
        raise SkillEstimateError(
            "A newer Codeforces sync exists; rebuild progress then skills for uid " + str(uid)
        )

    all_tags = db.session.execute(
        db.select(UserTopicMastery).where(
            UserTopicMastery.uid == uid,
            UserTopicMastery.source_account_id == account.id,
        ).order_by(UserTopicMastery.tag)
    ).scalars().all()
    sliced = all_tags[offset:offset + limit]
    return {
        "uid": uid,
        "codeforces_account_id": account.id,
        "handle": account.handle,
        "ownership_verified": account.ownership_verified,
        "source_sync_status": account.sync_status,
        "source_sync_succeeded": account.sync_status == "SUCCEEDED",
        "history_completeness": "not_verified",
        "model_version": MODEL_VERSION,
        "difficulty_readiness": summary.to_dict(),
        "topic_pagination": {"limit": limit, "offset": offset, "total": len(all_tags), "returned": len(sliced)},
        "topics": [row.to_dict() for row in sliced],
        "notes": [
            "No topic row means no observed exposure, not zero mastery.",
            "A null mastery score means insufficient decided evidence.",
            "These estimates describe linked public history; Codeforces handle ownership is not verified.",
        ],
    }
