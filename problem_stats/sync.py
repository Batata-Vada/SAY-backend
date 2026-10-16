"""Atomic Codeforces-only problem catalog synchronization."""

from datetime import datetime, timezone

from database.db import db
from models.problem import Problem
from problem_stats.codeforces import fetch_codeforces_problems

PLATFORM = "CODEFORCES"

# Attributes already present in the current Problem schema.
UPDATABLE_FIELDS = (
    "title",
    "slug",
    "url",
    "contest_id",
    "problem_index",
    "category",
    "difficulty_raw",
    "tags_raw",
    "stats_raw",
    "metadata_raw",
)


def _validate_catalog(catalog):
    """Reject dangerous partial/ambiguous fetch results before database writes."""
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Refusing to sync an empty Codeforces catalog")

    seen = set()
    for item in catalog:
        if not isinstance(item, dict) or item.get("platform") != PLATFORM:
            raise ValueError("Catalog includes a non-Codeforces or malformed entry")

        external_id = item.get("external_id")
        if not isinstance(external_id, str) or not external_id:
            raise ValueError("Problem has no stable external_id")
        if external_id in seen:
            raise ValueError(f"Duplicate Codeforces external_id: {external_id}")
        seen.add(external_id)

        for key in ("title", "url"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError(f"Problem {external_id} has invalid {key}")


def sync_codeforces_problems():
    """Fetch all Codeforces problems and upsert them in one DB transaction.

    No intermediate commits. If anything fails, rollback removes all changes
    from this run. Existing records for other platforms are left untouched.
    Must be called inside a Flask application context.
    """
    catalog = fetch_codeforces_problems()  # Network happens before DB writes.
    _validate_catalog(catalog)
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0
    unchanged = 0

    try:
        # One query replaces an N+1 lookup for every fetched problem.
        existing = {
            row.external_id: row
            for row in db.session.execute(
                db.select(Problem).where(Problem.platform == PLATFORM)
            ).scalars()
        }

        for item in catalog:
            external_id = item["external_id"]
            problem = existing.get(external_id)
            is_new = problem is None

            if is_new:
                problem = Problem(
                    platform=PLATFORM,
                    external_id=external_id,
                    first_seen_at=now,
                )
                db.session.add(problem)
                existing[external_id] = problem
                inserted += 1
            else:
                changed = any(
                    getattr(problem, field) != item.get(field)
                    for field in UPDATABLE_FIELDS
                )
                if changed:
                    updated += 1
                else:
                    unchanged += 1

            for field in UPDATABLE_FIELDS:
                setattr(problem, field, item.get(field))

            problem.last_seen_at = now
            problem.last_fetched_at = now

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "platform": PLATFORM,
        "fetched": len(catalog),
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "synced_at": now.isoformat(),
    }