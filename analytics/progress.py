"""Rebuild and read materialized progress from official Codeforces submissions."""

from sqlalchemy import func

from analytics.aggregation import aggregate_submissions, as_utc
from database.db import db
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from models.problem import Problem
from models.user_problem_progress import UserProblemProgress
from models.users import User


class ProgressBuildError(RuntimeError):
    pass


def active_codeforces_account(uid):
    return db.session.execute(
        db.select(CodeforcesAccount).where(
            CodeforcesAccount.uid == uid,
            CodeforcesAccount.unlinked_at.is_(None),
        )
    ).scalar_one_or_none()


def _resolved_individual_query(account_id):
    # The JOIN explicitly excludes cross-platform records and unresolved IDs.
    return (
        db.select(CodeforcesSubmission)
        .join(Problem, CodeforcesSubmission.problem_id == Problem.id)
        .where(
            CodeforcesSubmission.codeforces_account_id == account_id,
            CodeforcesSubmission.attribution_status == "INDIVIDUAL",
            Problem.platform == "CODEFORCES",
        )
    )


def rebuild_user_progress(uid: int) -> dict:
    """Atomically replace all uid aggregates using only the active CF account.

    Deterministic business fields and progress_updated_at depend solely on
    official submission rows. Earlier archived links are deliberately excluded.
    Never reads `models.submission.Submission` (local saved source files).
    """
    if type(uid) is not int or uid < 1:
        raise ValueError("uid must be a positive integer")
    if db.session.get(User, uid) is None:
        raise ProgressBuildError("SAY user not found")

    account = active_codeforces_account(uid)
    if account is None:
        raise ProgressBuildError("User has no active Codeforces account")
    if account.sync_status == "RUNNING":
        raise ProgressBuildError("Wait until Codeforces submission import has finished")

    try:
        # Query all qualifying rows once. Reasonable for a Phase 1 CLI job.
        source_rows = db.session.execute(
            _resolved_individual_query(account.id)
        ).scalars().all()
        aggregates = aggregate_submissions(source_rows)

        # One atomic replacement; exceptions roll back and preserve old snapshot.
        db.session.execute(
            db.delete(UserProblemProgress).where(UserProblemProgress.uid == uid)
        )
        for problem_id, result in aggregates.items():
            db.session.add(UserProblemProgress(
                uid=uid,
                problem_id=problem_id,
                source_account_id=account.id,
                official_submission_count=result.official_submission_count,
                official_failure_count=result.official_failure_count,
                official_final_ok_count=result.official_final_ok_count,
                official_pending_count=result.official_pending_count,
                official_provisional_ok_count=result.official_provisional_ok_count,
                official_unclassified_count=result.official_unclassified_count,
                is_solved=result.is_solved,
                first_attempted_at=result.first_attempted_at,
                first_solved_at=result.first_solved_at,
                last_submitted_at=result.last_submitted_at,
                progress_updated_at=result.progress_updated_at,
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "uid": uid,
        "codeforces_account_id": account.id,
        "handle": account.handle,
        "distinct_attempted_problems": len(aggregates),
        "distinct_solved_problems": sum(x.is_solved for x in aggregates.values()),
        "qualifying_official_submissions": sum(x.official_submission_count for x in aggregates.values()),
        "official_failures": sum(x.official_failure_count for x in aggregates.values()),
        "evidence_diagnostics": _evidence_diagnostics(account.id),
        "source_sync_status": account.sync_status,
        "source_history_synced": account.sync_status == "SUCCEEDED" and account.last_synced_at is not None,
    }


def _evidence_diagnostics(account_id):
    """Explain exclusions rather than silently implying imported == attributed."""
    return {
        "all_imported_official_submissions": db.session.execute(
            db.select(func.count(CodeforcesSubmission.id)).where(
                CodeforcesSubmission.codeforces_account_id == account_id
            )
        ).scalar_one(),
        "unresolved_problem_submissions": db.session.execute(
            db.select(func.count(CodeforcesSubmission.id)).where(
                CodeforcesSubmission.codeforces_account_id == account_id,
                CodeforcesSubmission.problem_id.is_(None),
            )
        ).scalar_one(),
        "non_individual_submissions": db.session.execute(
            db.select(func.count(CodeforcesSubmission.id)).where(
                CodeforcesSubmission.codeforces_account_id == account_id,
                CodeforcesSubmission.attribution_status != "INDIVIDUAL",
            )
        ).scalar_one(),
    }


def _latest_source_check(account_id):
    return db.session.execute(
        db.select(func.max(CodeforcesSubmission.last_checked_at))
        .join(Problem, CodeforcesSubmission.problem_id == Problem.id)
        .where(
            CodeforcesSubmission.codeforces_account_id == account_id,
            CodeforcesSubmission.attribution_status == "INDIVIDUAL",
            Problem.platform == "CODEFORCES",
        )
    ).scalar_one()


def read_user_progress(uid: int, *, limit: int = 50, offset: int = 0) -> dict:
    """Read an explicitly rebuilt snapshot; signal if official evidence changed."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    account = active_codeforces_account(uid)
    if account is None:
        raise ProgressBuildError("User has no active Codeforces account")

    q = db.select(UserProblemProgress).where(
        UserProblemProgress.uid == uid,
        UserProblemProgress.source_account_id == account.id,
    )
    totals = db.session.execute(
        db.select(
            func.count(UserProblemProgress.problem_id),
            func.coalesce(func.sum(db.cast(UserProblemProgress.is_solved, db.Integer)), 0),
            func.coalesce(func.sum(UserProblemProgress.official_submission_count), 0),
            func.coalesce(func.sum(UserProblemProgress.official_failure_count), 0),
            func.max(UserProblemProgress.progress_updated_at),
        ).where(
            UserProblemProgress.uid == uid,
            UserProblemProgress.source_account_id == account.id,
        )
    ).one()
    attempted, solved, submission_count, failures, snapshot_latest = totals
    source_latest = _latest_source_check(account.id)
    needs_rebuild = as_utc(source_latest) != as_utc(snapshot_latest)

    # A relink with no current source should not display the previous account.
    entries = db.session.execute(
        db.select(UserProblemProgress, Problem)
        .join(Problem, UserProblemProgress.problem_id == Problem.id)
        .where(
            UserProblemProgress.uid == uid,
            UserProblemProgress.source_account_id == account.id,
            Problem.platform == "CODEFORCES",
        )
        .order_by(UserProblemProgress.last_submitted_at.desc(), UserProblemProgress.problem_id)
        .limit(limit)
        .offset(offset)
    ).all()

    return {
        "uid": uid,
        "codeforces_account_id": account.id,
        "handle": account.handle,
        "ownership_verified": account.ownership_verified,
        "source_sync_status": account.sync_status,
        "source_history_synced": account.sync_status == "SUCCEEDED" and account.last_synced_at is not None,
        "needs_rebuild": needs_rebuild,
        "distinct_attempted_problems": attempted,
        "distinct_solved_problems": int(solved),
        "qualifying_official_submissions": int(submission_count),
        "official_failures": int(failures),
        "evidence_diagnostics": _evidence_diagnostics(account.id),
        "pagination": {"limit": limit, "offset": offset, "returned": len(entries)},
        "problems": [progress.to_dict(problem) for progress, problem in entries],
    }
