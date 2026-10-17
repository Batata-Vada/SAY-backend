"""Idempotent, resumable Codeforces user.status ingestion (CLI, not HTTP).

Each page commits independently. On failure the successful watermark is not
advanced; a retry safely revisits already committed pages. A periodic --full
run is needed to detect arbitrarily old rejudges.
"""
import logging
from datetime import datetime, timedelta, timezone

from database.db import db
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from codeforces.client import CodeforcesClient, CodeforcesUnavailable
from codeforces.rate_limit import exclusive_account_sync
from codeforces.reconciliation import (
    codeforces_problem_lookup,
    normalize_submission,
    InvalidCodeforcesSubmission,
    reconcile_unresolved_submissions,
)

logger = logging.getLogger(__name__)

# last_checked_at is always refreshed, but not counted as a verdict/data change.
_FIELDS = (
    "problem_id", "cf_contest_id", "cf_problem_index", "cf_problemset_name",
    "cf_problem_name", "cf_problem_external_id", "verdict", "testset",
    "programming_language", "submitted_at", "time_consumed_ms",
    "memory_consumed_bytes", "passed_test_count", "participant_type",
    "attribution_status", "author_members_raw", "raw_problem",
)


class SubmissionSyncError(RuntimeError):
    pass


def _as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _apply_page(account_id, handle, raw_page, lookup, seen_ids, stats, *, force_refresh=False):
    """Normalize whole page first; then upsert using one batch lookup and commit."""
    if not isinstance(raw_page, list):
        raise SubmissionSyncError("Invalid paginated submissions payload")
    now = datetime.now(timezone.utc)
    parsed = []
    newly_seen = 0
    page_ids = set()
    for raw in raw_page:
        row = normalize_submission(raw, handle, lookup, now)
        sid = row["cf_submission_id"]
        if sid in page_ids:
            raise SubmissionSyncError("Duplicate official ID in the same API page")
        page_ids.add(sid)
        # Repeated IDs between pages may arise when offsets shift.
        if sid not in seen_ids:
            newly_seen += 1
            seen_ids.add(sid)
            parsed.append(row)
        elif force_refresh:
            parsed.append(row)

    ids = [row["cf_submission_id"] for row in parsed]
    existing = {}
    if ids:
        existing = {
            row.cf_submission_id: row
            for row in db.session.execute(
                db.select(CodeforcesSubmission).where(
                    CodeforcesSubmission.codeforces_account_id == account_id,
                    CodeforcesSubmission.cf_submission_id.in_(ids),
                )
            ).scalars()
        }

    for incoming in parsed:
        sid = incoming["cf_submission_id"]
        stored = existing.get(sid)
        if stored is None:
            stored = CodeforcesSubmission(
                codeforces_account_id=account_id,
                cf_submission_id=sid,
            )
            db.session.add(stored)
            stats["inserted"] += 1
        else:
            stats["previously_known"] += 1
            if any(
                (_as_utc(getattr(stored, f)) != _as_utc(incoming[f]))
                if f == "submitted_at" else (getattr(stored, f) != incoming[f])
                for f in _FIELDS
            ):
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1

        for key, value in incoming.items():
            setattr(stored, key, value)

    db.session.commit()
    stats["unique_seen"] += newly_seen
    stats["pages_completed"] += 1
    return parsed


def _error_label(error):
    if isinstance(error, CodeforcesUnavailable):
        return "Codeforces API unavailable or returned an error"
    if isinstance(error, InvalidCodeforcesSubmission):
        return "Codeforces returned an invalid submission record"
    if isinstance(error, SubmissionSyncError):
        return "Submission synchronization consistency check failed"
    return "Submission synchronization failed; see server logs"


def sync_codeforces_submissions(
    account_id, *, full=False, page_size=500, overlap=100,
    lookback_days=14, client=None, max_pages=None,
):
    """Synchronize linked Codeforces submissions for one local account record.

    Runs inside an application context. Never called from a Flask HTTP route.
    `full=True` scans to the end and also finds old rejudges.
    `max_pages` is a diagnostic safety cap; hitting it raises an error, leaving
    the successful watermark unchanged.
    """
    if type(account_id) is not int or account_id < 1:
        raise ValueError("account_id must be a positive integer")
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise ValueError("page_size must be in 1..1000")
    if type(overlap) is not int or overlap < 0:
        raise ValueError("overlap must be non-negative")
    if type(lookback_days) is not int or lookback_days < 0:
        raise ValueError("lookback_days must be non-negative")
    if max_pages is not None and (type(max_pages) is not int or max_pages < 1):
        raise ValueError("max_pages must be positive")

    with exclusive_account_sync(account_id):
        account = db.session.get(CodeforcesAccount, account_id)
        if account is None or account.unlinked_at is not None:
            raise SubmissionSyncError("Active Codeforces account not found")
        handle = account.handle
        prior_success = _as_utc(account.last_synced_at)
        cutoff = None if (full or prior_success is None) else (
            prior_success - timedelta(days=lookback_days)
        )
        # Pending and preliminary verdicts can be older than ordinary overlap.
        if cutoff is not None:
            unresolved_times = db.session.execute(
                db.select(CodeforcesSubmission.submitted_at).where(
                    CodeforcesSubmission.codeforces_account_id == account_id,
                    db.or_(
                        CodeforcesSubmission.verdict.is_(None),
                        db.and_(
                            CodeforcesSubmission.verdict == "OK",
                            db.or_(CodeforcesSubmission.testset.is_(None),
                                   CodeforcesSubmission.testset != "TESTS"),
                        ),
                    ),
                ).order_by(CodeforcesSubmission.submitted_at.asc()).limit(1)
            ).scalar_one_or_none()
            if unresolved_times is not None:
                cutoff = min(cutoff, _as_utc(unresolved_times) - timedelta(days=1))

        account.sync_status = "RUNNING"
        account.last_sync_error = None
        db.session.commit()

        stats = {
            "account_id": account_id, "handle": handle,
            "mode": "FULL" if cutoff is None else "INCREMENTAL",
            "inserted": 0, "updated": 0, "unchanged": 0,
            "previously_known": 0, "unique_seen": 0, "pages_completed": 0,
            "reconciled_problem_links": 0,
        }

        try:
            client = client or CodeforcesClient()
            # Refuse a potentially reassigned/renamed handle without review.
            info = client.user_info(handle)
            canonical = info.get("handle")
            if not isinstance(canonical, str) or canonical.casefold() != handle.casefold():
                raise SubmissionSyncError(
                    "Codeforces canonical handle changed; review/relink before importing"
                )
            registration = info.get("registrationTimeSeconds")
            if (account.registration_time_seconds is not None
                    and registration != account.registration_time_seconds):
                raise SubmissionSyncError("Codeforces account identity changed; review link")

            lookup = codeforces_problem_lookup()
            seen_ids = set()
            start = 1
            minimum_pages = 2  # Never stop merely because one known ID occurs.
            while True:
                if max_pages is not None and stats["pages_completed"] >= max_pages:
                    raise SubmissionSyncError("Page cap reached before a complete sync")
                raw_page = client.user_status(handle, from_index=start, count=page_size)
                if not isinstance(raw_page, list):
                    raise SubmissionSyncError("Invalid API page")
                if not raw_page:
                    break
                parsed = _apply_page(account_id, handle, raw_page, lookup, seen_ids, stats)
                logger.info("CF account %s: scanned %s submissions", account_id, len(seen_ids))
                if len(raw_page) < page_size:
                    break

                oldest = min(item["submitted_at"] for item in parsed) if parsed else None
                if (cutoff is not None and oldest is not None
                        and oldest <= cutoff
                        and stats["previously_known"] >= overlap
                        and stats["pages_completed"] >= minimum_pages):
                    break
                start += len(raw_page)

            # Re-read page one in case new submissions arrived while paging.
            # Revisited IDs were already seen; new top-page IDs are upserted.
            head_page = client.user_status(handle, from_index=1, count=page_size)
            _apply_page(account_id, handle, head_page, lookup, seen_ids, stats, force_refresh=True)

            # Link submissions that predate a newly ingested problem catalog.
            stats["reconciled_problem_links"] = reconcile_unresolved_submissions(account_id)
            account = db.session.get(CodeforcesAccount, account_id)
            account.sync_status = "SUCCEEDED"
            account.last_sync_error = None
            account.last_synced_at = datetime.now(timezone.utc)
            db.session.commit()
            stats["last_synced_at"] = account.last_synced_at.isoformat()
            return stats
        except Exception as exc:
            db.session.rollback()
            logger.exception("Official Codeforces submission sync failed for account %s", account_id)
            failed = db.session.get(CodeforcesAccount, account_id)
            if failed is not None:
                failed.sync_status = "FAILED"
                failed.last_sync_error = _error_label(exc)
                # last_synced_at must remain unchanged on failure.
                db.session.commit()
            raise
