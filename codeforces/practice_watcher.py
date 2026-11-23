"""Run Codeforces practice synchronization separately from the Flask web server."""
import json
import logging
import time

import click
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func

from analytics.mastery import SkillEstimateError, read_user_skills, rebuild_user_skills
from analytics.progress import read_user_progress, rebuild_user_progress
from codeforces.submission_sync import sync_active_practice_submissions
from codeforces.sync_queue import process_one_sync_request, enqueue_sync, SyncAlreadyQueued
from problem_stats.sync import sync_codeforces_problems
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
    # A manually finished session can still receive a delayed final verdict.
    # Watch recent finished sessions as well, without reopening their timers.
    recent = datetime.now(timezone.utc) - timedelta(minutes=15)
    rows = db.session.execute(
        db.select(CodeforcesAccount.id, CodeforcesAccount.uid, func.min(PracticeSession.started_at))
        .join(PracticeSession, PracticeSession.source_account_id == CodeforcesAccount.id)
        .where(
            db.or_(
                PracticeSession.status == "ACTIVE",
                db.and_(
                    PracticeSession.status == "FINISHED",
                    PracticeSession.finished_at.is_not(None),
                    PracticeSession.finished_at >= recent,
                ),
            ),
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
    failed = 0
    for account_id, uid, first_started_at in due[:limit]:
        last_polled[account_id] = time.monotonic()
        try:
            stats = sync_active_practice_submissions(
                account_id, started_at=first_started_at, max_pages=max_pages
            )
            result = complete_verified_sessions(account_id)
            completed += result["completed"]
            if (
                stats["inserted"] or stats["updated"]
                or stats["reconciled_problem_links"] or result["completed"]
            ):
                rebuild_user_progress(uid)
                rebuild_user_skills(uid)
            checked += 1
            logger.info(
                "Practice poll account=%s inserted=%s updated=%s finished=%s",
                account_id, stats["inserted"], stats["updated"], result["completed"],
            )
        except Exception:
            failed += 1
            db.session.rollback()
            logger.exception("Automatic practice sync failed for account %s", account_id)
        finally:
            db.session.remove()
    active_ids = {row[0] for row in rows}
    for account_id in set(last_polled) - active_ids:
        del last_polled[account_id]
    return {
        "eligible_accounts": len(rows),
        "accounts_due": len(due),
        "accounts_checked": checked,
        "accounts_failed": failed,
        "sessions_completed": completed,
    }


def schedule_full_history_refresh(*, now=None):
    """Queue due full-history syncs for verified active links once per configured interval."""
    now = now or datetime.now(timezone.utc)
    interval = current_app.config["CODEFORCES_FULL_SYNC_INTERVAL_HOURS"]
    if not 1 <= interval <= 720:
        raise ValueError("CODEFORCES_FULL_SYNC_INTERVAL_HOURS must be between 1 and 720")
    cutoff = now - timedelta(hours=interval)
    account = db.session.execute(
        db.select(CodeforcesAccount)
        .where(
            CodeforcesAccount.ownership_verified.is_(True),
            CodeforcesAccount.unlinked_at.is_(None),
            db.or_(
                CodeforcesAccount.last_full_sync_at.is_(None),
                CodeforcesAccount.last_full_sync_at <= cutoff,
            ),
            CodeforcesAccount.sync_status != "RUNNING",
        )
        .order_by(CodeforcesAccount.last_full_sync_at.asc(), CodeforcesAccount.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if account is None:
        return False
    try:
        enqueue_sync(account.uid, account, full=True)
        click.echo(f"Queued periodic full Codeforces refresh for account {account.id}")
        return True
    except SyncAlreadyQueued:
        return False


def repair_stale_profiles(*, after_account_id=0, batch_size=5):
    """Repair progress and skills after interrupted syncs or catalog changes.

    Only successfully synchronized, currently linked accounts are eligible.
    Cycling account IDs avoids starving users behind an unhealthy account.
    """
    if type(after_account_id) is not int or after_account_id < 0:
        raise ValueError("Invalid repair cursor")
    if type(batch_size) is not int or not 1 <= batch_size <= 20:
        raise ValueError("Invalid repair batch size")

    def batch(cursor):
        return db.session.execute(
            db.select(CodeforcesAccount.id, CodeforcesAccount.uid)
            .where(
                CodeforcesAccount.id > cursor,
                CodeforcesAccount.unlinked_at.is_(None),
                CodeforcesAccount.ownership_verified.is_(True),
                CodeforcesAccount.sync_status == "SUCCEEDED",
                CodeforcesAccount.last_synced_at.is_not(None),
            )
            .order_by(CodeforcesAccount.id.asc())
            .limit(batch_size)
        ).all()

    accounts = batch(after_account_id)
    if not accounts and after_account_id:
        accounts = batch(0)
    result = {
        "accounts_checked": 0,
        "profiles_repaired": 0,
        "accounts_failed": 0,
        "next_account_id": accounts[-1][0] if accounts else 0,
    }
    for account_id, uid in accounts:
        try:
            progress = read_user_progress(uid, limit=1, offset=0)
            updated = bool(progress["needs_rebuild"])
            if updated:
                rebuild_user_progress(uid)
            try:
                read_user_skills(uid, limit=1, offset=0)
            except SkillEstimateError:
                rebuild_user_skills(uid)
                updated = True
            result["profiles_repaired"] += int(updated)
            result["accounts_checked"] += 1
        except Exception:
            result["accounts_failed"] += 1
            db.session.rollback()
            logger.exception("Failed to repair Codeforces profile for account %s", account_id)
        finally:
            db.session.remove()
    return result


def run_worker():
    """Continuously watch practice and also execute the existing sync queue."""
    interval = current_app.config["CODEFORCES_WATCH_INTERVAL_SECONDS"]
    if not 10 <= interval <= 3600:
        raise ValueError("CODEFORCES_WATCH_INTERVAL_SECONDS must be between 10 and 3600")
    if not 1 <= current_app.config["CODEFORCES_WATCH_BATCH_SIZE"] <= 100:
        raise ValueError("CODEFORCES_WATCH_BATCH_SIZE must be between 1 and 100")
    if not 1 <= current_app.config["CODEFORCES_WATCH_PAGE_LIMIT"] <= 100:
        raise ValueError("CODEFORCES_WATCH_PAGE_LIMIT must be between 1 and 100")
    click.echo(f"Codeforces practice watcher started; interval={interval}s")
    last_polled = {}
    first_cycle = True
    last_full_schedule = 0.0
    last_catalog_sync = 0.0
    last_profile_repair = 0.0
    profile_cursor = 0
    while True:
        try:
            summary = watch_once(last_polled=last_polled)
            if first_cycle or summary["accounts_due"]:
                click.echo("Practice watcher: " + json.dumps(summary, sort_keys=True))
            first_cycle = False
        except Exception:
            logger.exception("Practice watcher cycle failed")
        finally:
            db.session.remove()
        try:
            now = time.monotonic()
            if now - last_full_schedule >= 3600:
                last_full_schedule = now
                schedule_full_history_refresh()
            result = process_one_sync_request()
            if result is not None:
                click.echo("Codeforces sync: " + json.dumps(result, sort_keys=True))
        except Exception:
            logger.exception("Queued Codeforces sync worker failed")
        finally:
            db.session.remove()
        try:
            now = time.monotonic()
            if current_app.config["CODEFORCES_AUTO_CATALOG_SYNC"] and (
                last_catalog_sync == 0.0
                or now - last_catalog_sync >= current_app.config["CODEFORCES_CATALOG_INTERVAL_HOURS"] * 3600
            ):
                last_catalog_sync = now
                result = sync_codeforces_problems()
                click.echo("Codeforces catalog: " + json.dumps(result, sort_keys=True))
        except Exception:
            db.session.rollback()
            logger.exception("Scheduled Codeforces problem catalog refresh failed")
        finally:
            db.session.remove()
        try:
            now = time.monotonic()
            if now - last_profile_repair >= 60:
                last_profile_repair = now
                repaired = repair_stale_profiles(after_account_id=profile_cursor)
                profile_cursor = repaired["next_account_id"]
                if repaired["profiles_repaired"] or repaired["accounts_failed"]:
                    click.echo("Codeforces profile repair: " + json.dumps(repaired, sort_keys=True))
        except Exception:
            db.session.rollback()
            logger.exception("Automatic Codeforces progress/skills repair failed")
        finally:
            db.session.remove()
        time.sleep(5)
