"""Persistent Step 9 refresh queue and one-shot worker.

Run the worker from a separate process (e.g. systemd or a development shell).
Do not spawn unreliable in-process background threads from Flask routes.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from database.db import db
from models.codeforces_account import CodeforcesAccount
from models.codeforces_sync_request import CodeforcesSyncRequest
from codeforces.submission_sync import sync_codeforces_submissions
from analytics.progress import rebuild_user_progress
from analytics.mastery import rebuild_user_skills

logger = logging.getLogger(__name__)


class SyncAlreadyQueued(RuntimeError):
    pass


def latest_sync_request(account_id):
    return db.session.execute(
        db.select(CodeforcesSyncRequest)
        .where(CodeforcesSyncRequest.codeforces_account_id == account_id)
        .order_by(CodeforcesSyncRequest.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def enqueue_sync(uid, account, *, full=False):
    """Atomically enqueue at most one open job per linked account.

    Database uniqueness handles concurrent requests. Does not touch
    CodeforcesAccount.last_synced_at or falsely claim a sync completed.
    """
    if account.uid != uid or account.unlinked_at is not None:
        raise ValueError("Account is not the user's active link")
    if account.sync_status == "RUNNING":
        raise SyncAlreadyQueued("Codeforces sync already running")
    job = CodeforcesSyncRequest(
        uid=uid, codeforces_account_id=account.id,
        full=full, status="QUEUED",
    )
    try:
        db.session.add(job)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise SyncAlreadyQueued("Codeforces sync already queued or running") from exc
    return job


def _claim_next_job():
    """Claim by conditional UPDATE, safe against two cooperating worker processes."""
    while True:
        id_to_claim = db.session.execute(
            db.select(CodeforcesSyncRequest.id)
            .where(CodeforcesSyncRequest.status == "QUEUED")
            .order_by(CodeforcesSyncRequest.id)
            .limit(1)
        ).scalar_one_or_none()
        if id_to_claim is None:
            return None
        now = datetime.now(timezone.utc)
        updated = db.session.execute(
            db.update(CodeforcesSyncRequest)
            .where(CodeforcesSyncRequest.id == id_to_claim,
                   CodeforcesSyncRequest.status == "QUEUED")
            .values(status="RUNNING", started_at=now)
        )
        db.session.commit()
        if updated.rowcount == 1:
            return id_to_claim
        db.session.expire_all()


def process_one_sync_request():
    """Process one queued job; returns a sanitized summary or None if empty.

    Official submission imports commit pages independently. Failure is reported
    in job status; the importer preserves its last successful sync watermark.
    """
    job_id = _claim_next_job()
    if job_id is None:
        return None
    job = db.session.get(CodeforcesSyncRequest, job_id)
    account = db.session.get(CodeforcesAccount, job.codeforces_account_id)
    if (account is None or account.unlinked_at is not None
            or account.uid != job.uid):
        job.status = "CANCELLED"
        job.error_message = "Linked Codeforces account changed before the queued sync began"
        job.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"job_id": job_id, "status": "CANCELLED"}
    try:
        result = sync_codeforces_submissions(account.id, full=job.full)
        # Step 5 already performs problem reconciliation on a successful import.
        progress = rebuild_user_progress(job.uid)
        skills = rebuild_user_skills(job.uid)
        job = db.session.get(CodeforcesSyncRequest, job_id)
        job.status = "SUCCEEDED"
        job.result_raw = {
            "submission_sync": result,
            "progress": {
                "distinct_attempted_problems": progress["distinct_attempted_problems"],
                "distinct_solved_problems": progress["distinct_solved_problems"],
            },
            "skills": {
                "model_version": skills["model_version"],
                "readiness_rating": skills["readiness_rating"],
            },
        }
        job.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"job_id": job_id, "status": "SUCCEEDED"}
    except Exception:
        logger.exception("Codeforces sync job %s failed", job_id)
        db.session.rollback()
        job = db.session.get(CodeforcesSyncRequest, job_id)
        if job is not None:
            job.status = "FAILED"
            job.error_message = (
                "Sync or downstream progress/skill rebuild failed; "
                "inspect worker logs before retrying"
            )
            job.finished_at = datetime.now(timezone.utc)
            db.session.commit()
        return {"job_id": job_id, "status": "FAILED"}
