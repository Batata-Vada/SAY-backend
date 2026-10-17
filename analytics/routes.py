"""Read-only authenticated student progress and skill endpoints."""

from flask import Blueprint, request

from middleware.auth import login_required
from analytics.progress import ProgressBuildError, read_user_progress
from analytics.mastery import SkillEstimateError, read_user_skills

analytics = Blueprint("analytics", __name__, url_prefix="/api/me")


def _pagination(default_limit=50):
    try:
        limit = int(request.args.get("limit", str(default_limit)))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    if not 1 <= limit <= 100 or offset < 0:
        return None
    return limit, offset


@analytics.get("/progress")
@login_required
def my_progress(user):
    pagination = _pagination()
    if pagination is None:
        return {"message": "limit must be 1..100 and offset >= 0"}, 400
    limit, offset = pagination
    try:
        data = read_user_progress(user.uid, limit=limit, offset=offset)
    except ProgressBuildError as exc:
        return {"message": str(exc)}, 404
    if data["needs_rebuild"]:
        return {
            "message": "Official evidence changed. Rebuild user progress before reading.",
            "command": f"flask --app main rebuild-cf-progress --uid {user.uid}",
            "codeforces_account_id": data["codeforces_account_id"],
        }, 409
    return data, 200


@analytics.get("/mastery")
@login_required
def my_mastery(user):
    pagination = _pagination(100)
    if pagination is None:
        return {"message": "limit must be 1..100 and offset >= 0"}, 400
    try:
        data = read_user_skills(user.uid, limit=pagination[0], offset=pagination[1])
    except SkillEstimateError as exc:
        return {"message": str(exc)}, 409
    return data, 200


@analytics.get("/difficulty-readiness")
@login_required
def my_difficulty_readiness(user):
    try:
        data = read_user_skills(user.uid, limit=1, offset=0)
    except SkillEstimateError as exc:
        return {"message": str(exc)}, 409
    return {
        "uid": data["uid"],
        "handle": data["handle"],
        "codeforces_account_id": data["codeforces_account_id"],
        "ownership_verified": data["ownership_verified"],
        "source_sync_status": data["source_sync_status"],
        "difficulty_readiness": data["difficulty_readiness"],
    }, 200
