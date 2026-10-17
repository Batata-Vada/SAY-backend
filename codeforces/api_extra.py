"""Read-only official submission endpoints and queued refresh API for Step 9.

The blueprint is registered once by main.py, separately from existing account
linking routes so the current codeforces/routes.py does not need replacement.
"""
from flask import Blueprint, request
from sqlalchemy import func

from database.db import db
from middleware.auth import login_required
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from codeforces.sync_queue import enqueue_sync, latest_sync_request, SyncAlreadyQueued

codeforces_api = Blueprint("codeforces_api", __name__, url_prefix="/api/codeforces")


def _active_account(uid):
    return db.session.execute(
        db.select(CodeforcesAccount).where(
            CodeforcesAccount.uid == uid,
            CodeforcesAccount.unlinked_at.is_(None),
        )
    ).scalar_one_or_none()


def _pagination():
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
    except (TypeError, ValueError):
        return None
    if not 1 <= limit <= 100 or offset < 0:
        return None
    return limit, offset


@codeforces_api.post("/sync")
@login_required
def request_sync(user):
    account = _active_account(user.uid)
    if account is None:
        return {"message": "Link a Codeforces account before requesting sync"}, 404
    data = request.get_json(silent=True)
    if data is None:
        if request.get_data(cache=True):
            return {"message": "Invalid JSON body"}, 400
        # An empty POST (without a JSON body) defaults to incremental.
        data = {}
    if not isinstance(data, dict) or set(data) - {"full"}:
        return {"message": "Provide a JSON object with optional boolean full"}, 400
    full = data.get("full", False)
    if type(full) is not bool:
        return {"message": "full must be a JSON boolean"}, 400
    try:
        job = enqueue_sync(user.uid, account, full=full)
    except SyncAlreadyQueued as exc:
        return {"message": str(exc)}, 409
    return {
        "message": "Sync queued; a separate worker processes requests",
        "job": job.to_dict(),
        "account_id": account.id,
        "status_url": "/api/codeforces/sync",
    }, 202, {"Location": "/api/codeforces/sync", "Cache-Control": "no-store"}


@codeforces_api.get("/sync")
@login_required
def read_sync_status(user):
    account = _active_account(user.uid)
    if account is None:
        return {"message": "No Codeforces account linked"}, 404
    recent = latest_sync_request(account.id)
    return {
        "account": account.to_dict(),
        "job": recent.to_dict() if recent else None,
        "note": "Status reflects this active link only; a queued job requires a running worker.",
    }, 200, {"Cache-Control": "no-store"}


@codeforces_api.get("/submissions")
@login_required
def list_official_submissions(user):
    account = _active_account(user.uid)
    if account is None:
        return {"message": "No Codeforces account linked"}, 404
    page = _pagination()
    if page is None:
        return {"message": "limit must be 1..100 and offset >= 0"}, 400
    limit, offset = page
    verdict = request.args.get("verdict")
    if verdict is not None and (not 1 <= len(verdict) <= 64 or not verdict.replace("_", "").isalnum()):
        return {"message": "Invalid verdict filter"}, 400
    conditions = [CodeforcesSubmission.codeforces_account_id == account.id]
    if verdict:
        conditions.append(CodeforcesSubmission.verdict == verdict)
    total = db.session.execute(
        db.select(func.count(CodeforcesSubmission.id)).where(*conditions)
    ).scalar_one()
    rows = db.session.execute(
        db.select(CodeforcesSubmission).where(*conditions)
        .order_by(CodeforcesSubmission.submitted_at.desc(),
                  CodeforcesSubmission.cf_submission_id.desc())
        .limit(limit).offset(offset)
    ).scalars().all()

    def serialize(s):
        return {
            "cf_submission_id": s.cf_submission_id,
            "problem_id": s.problem_id,
            "external_id": s.cf_problem_external_id,
            "problem_name": s.cf_problem_name,
            "verdict": s.verdict,
            "testset": s.testset,
            "attribution_status": s.attribution_status,
            "participant_type": s.participant_type,
            "programming_language": s.programming_language,
            "submitted_at": s.submitted_at.isoformat(),
            "is_final_individual_solve": s.is_final_individual_solve,
            "time_consumed_ms": s.time_consumed_ms,
            "memory_consumed_bytes": s.memory_consumed_bytes,
        }

    return {
        "account_id": account.id,
        "handle": account.handle,
        "total": total,
        "pagination": {"limit": limit, "offset": offset, "returned": len(rows)},
        "submissions": [serialize(row) for row in rows],
    }, 200, {"Cache-Control": "private, no-store"}
