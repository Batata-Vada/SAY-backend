"""Run Codeforces practice synchronization separately from the Flask web server."""
import logging
import time
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func

from analytics.mastery import rebuild_user_skills
from analytics.progress import rebuild_user_progress
from codeforces.submission_sync import sync_active_practice_submissions
from codeforces.sync_queue import process_one_sync_request
from database.db import db
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from models.practice_session import PracticeSession

logger = logging.getLogger(__name__)
MAX_SECONDS = 14400


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def complete_verified_sessions(account_id, *, now=None):
    """Finish active sessions using official accepted submission time, not poll time."""
    now = now or datetime.now(timezone.utc)
    sessions = db.session.execute(
        db.select(PracticeSession).where(
            PracticeSession.source_account_id == account_id,
            PracticeSession.status == "ACTIVE",
        )
    ).scalars().all()
    completed = 0
    abandoned = 0
    for session in sessions:
        start = as_utc(session.started_at)
        deadline = start + timedelta(seconds=MAX_SECONDS)
        accepted = db.session.execute(
            db.select(CodeforcesSubmission).where(
                CodeforcesSubmission.codeforces_account_id == account_id,
                CodeforcesSubmission.problem_id == session.problem_id,
                CodeforcesSubmission.attribution_status == "INDIVIDUAL",
                CodeforcesSubmission.verdict == "OK",
                CodeforcesSubmission.testset == "TESTS",
                CodeforcesSubmission.submitted_at >= session.started_at,
                CodeforcesSubmission.submitted_at <= deadline,
            ).order_by(
                CodeforcesSubmission.submitted_at.asc(),
                CodeforcesSubmission.cf_submission_id.asc(),
            ).limit(1)
        ).scalar_one_or_none()
        if accepted is not None:
            duration = int((as_utc(accepted.submitted_at) - start).total_seconds())
            if duration >= 1:
                session.status = "FINISHED"
                session.finished_at = accepted.submitted_at
                session.duration_seconds = duration
                completed += 1
                continue
        if now >= deadline:
            session.status = "ABANDONED"
            session.finished_at = now
            abandoned += 1
    if completed or abandoned:
        db.session.commit()
    return {"completed": completed, "abandoned": abandoned}


def watch_once(*, last_polled=None):
    """Check currently active verified accounts; return a log-friendly summary."""
    last_polled = last_polled if last_polled is not None else {}
    interval = current_app.config["CODEFORCES_WATCH_INTERVAL_SECONDS"]
    limit = current_app.config["CODEFORCES_WATCH_BATCH_SIZE"]
    max_pages = current_app.config["CODEFORCES_WATCH_PAGE_LIMIT"]
    rows = db.session.execute(
        db.select(CodeforcesAccount.id, CodeforcesAccount.uid, func.min(PracticeSession.started_at))
        .join(PracticeSession, PracticeSession.source_account_id == CodeforcesAccount.id)
        .where(
            PracticeSession.status == "ACTIVE",
            CodeforcesAccount.ownership_verified.is_(True),
            CodeforcesAccount.unlinked_at.is_(None),
        )
        .group_by(CodeforcesAccount.id, CodeforcesAccount.uid)
    ).all()
    now = time.monotonic()
    due = [
        row for row in rows
        if now - last_polled.get(row[0], float("-inf")) >= interval
    ]
    due.sort(key=lambda row: last_polled.get(row[0], float("-inf")))
    checked = 0
    completed = 0
    for account_id, uid, first_started_at in due[:limit]:
        last_polled[account_id] = time.monotonic()
        try:
            stats = sync_active_practice_submissions(
                account_id, started_at=first_started_at, max_pages=max_pages
            )
            result = complete_verified_sessions(account_id)
            completed += result["completed"]
            if stats["inserted"] or stats["updated"]:
                rebuild_user_progress(uid)
                rebuild_user_skills(uid)
            checked += 1
            logger.info(
                "Practice poll account=%s inserted=%s updated=%s finished=%s",
                account_id, stats["inserted"], stats["updated"], result["completed"],
            )
        except Exception:
            db.session.rollback()
            logger.exception("Automatic practice sync failed for account %s", account_id)
        finally:
            db.session.remove()
    active_ids = {row[0] for row in rows}
    for account_id in set(last_polled) - active_ids:
        del last_polled[account_id]
    return {"accounts_checked": checked, "sessions_completed": completed}


def run_worker():
    """Continuously watch practice and also execute the existing sync queue."""
    interval = current_app.config["CODEFORCES_WATCH_INTERVAL_SECONDS"]
    if not 10 <= interval <= 3600:
        raise ValueError("CODEFORCES_WATCH_INTERVAL_SECONDS must be between 10 and 3600")
    if not 1 <= current_app.config["CODEFORCES_WATCH_BATCH_SIZE"] <= 100:
        raise ValueError("CODEFORCES_WATCH_BATCH_SIZE must be between 1 and 100")
    if not 1 <= current_app.config["CODEFORCES_WATCH_PAGE_LIMIT"] <= 100:
        raise ValueError("CODEFORCES_WATCH_PAGE_LIMIT must be between 1 and 100")
    logger.info("Codeforces practice watcher started (poll every %ss)", interval)
    last_polled = {}
    while True:
        try:
            watch_once(last_polled=last_polled)
        except Exception:
            logger.exception("Practice watcher cycle failed")
        finally:
            db.session.remove()
        try:
            result = process_one_sync_request()
            if result is not None:
                logger.info("Queued Codeforces sync: %s", result)
        except Exception:
            logger.exception("Queued Codeforces sync worker failed")
        finally:
            db.session.remove()
        time.sleep(5)
