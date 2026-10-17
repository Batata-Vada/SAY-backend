"""Read-only authenticated student progress endpoints."""

from flask import Blueprint, request
from middleware.auth import login_required
from analytics.progress import ProgressBuildError, read_user_progress

analytics = Blueprint("analytics", __name__, url_prefix="/api/me")


@analytics.get("/progress")
@login_required
def my_progress(user):
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return {"message": "limit and offset must be integers"}, 400
    if not 1 <= limit <= 100 or offset < 0:
        return {"message": "limit must be 1..100 and offset must be >= 0"}, 400
    try:
        data = read_user_progress(user.uid, limit=limit, offset=offset)
    except ProgressBuildError as exc:
        return {"message": str(exc)}, 404
    if data["needs_rebuild"]:
        # Do not report stale data as authoritative after new syncs/rejudges.
        return {
            "message": "Official evidence changed. Rebuild user progress before reading.",
            "command": f"flask --app main rebuild-cf-progress --uid {user.uid}",
            "codeforces_account_id": data["codeforces_account_id"],
        }, 409
    return data, 200
