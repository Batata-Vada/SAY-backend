"""Normalize public submissions and resolve them against the Codeforces catalog."""
from datetime import datetime, timezone

from database.db import db
from models.problem import Problem
from models.codeforces_submission import CodeforcesSubmission


class InvalidCodeforcesSubmission(ValueError):
    """Reject malformed API data without moving the successful sync watermark."""


def problem_external_id(problem):
    """Must match problem_stats/codeforces.py's identity scheme."""
    if not isinstance(problem, dict):
        return None
    index = problem.get("index")
    if not isinstance(index, str) or not index:
        return None
    contest_id = problem.get("contestId")
    if type(contest_id) is int:
        return f"{contest_id}:{index}"
    problemset_name = problem.get("problemsetName")
    if isinstance(problemset_name, str) and problemset_name.strip():
        return f"{problemset_name}:{index}"
    return None


def codeforces_problem_lookup():
    """Codeforces only: never attach LeetCode/CSES/AtCoder records."""
    rows = db.session.execute(
        db.select(Problem.id, Problem.external_id).where(Problem.platform == "CODEFORCES")
    ).all()
    return {external_id: pk for pk, external_id in rows}


def _optional_nonnegative_int(value, field):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise InvalidCodeforcesSubmission(f"Invalid {field} in Codeforces response")
    return value


def normalize_submission(raw, account_handle, lookup, checked_at=None):
    if not isinstance(raw, dict):
        raise InvalidCodeforcesSubmission("Submission is not a JSON object")
    sid = raw.get("id")
    timestamp = raw.get("creationTimeSeconds")
    if type(sid) is not int or sid <= 0:
        raise InvalidCodeforcesSubmission("Submission is missing a valid official ID")
    if type(timestamp) is not int or timestamp <= 0:
        raise InvalidCodeforcesSubmission("Submission has an invalid timestamp")

    problem = raw.get("problem")
    if not isinstance(problem, dict):
        raise InvalidCodeforcesSubmission("Submission has no valid problem object")
    author = raw.get("author")
    if not isinstance(author, dict):
        author = {}
    members = author.get("members")
    if not isinstance(members, list):
        members = []
    handles = [m.get("handle") for m in members if isinstance(m, dict) and isinstance(m.get("handle"), str)]
    if len(members) > 1:
        attribution = "TEAM"
    elif len(members) == 1 and len(handles) == 1:
        attribution = ("INDIVIDUAL" if handles[0].casefold() == account_handle.casefold()
                       else "UNCERTAIN")
    else:
        attribution = "UNKNOWN"

    external_id = problem_external_id(problem)
    checked_at = checked_at or datetime.now(timezone.utc)
    contest_id = problem.get("contestId")
    return {
        "cf_submission_id": sid,
        "problem_id": lookup.get(external_id),
        "cf_contest_id": str(contest_id) if type(contest_id) is int else None,
        "cf_problem_index": problem.get("index") if isinstance(problem.get("index"), str) else None,
        "cf_problemset_name": problem.get("problemsetName") if isinstance(problem.get("problemsetName"), str) else None,
        "cf_problem_name": problem.get("name") if isinstance(problem.get("name"), str) else None,
        "cf_problem_external_id": external_id,
        "verdict": raw.get("verdict") if isinstance(raw.get("verdict"), str) else None,
        "testset": raw.get("testset") if isinstance(raw.get("testset"), str) else None,
        "programming_language": raw.get("programmingLanguage") if isinstance(raw.get("programmingLanguage"), str) else None,
        "submitted_at": datetime.fromtimestamp(timestamp, timezone.utc),
        "time_consumed_ms": _optional_nonnegative_int(raw.get("timeConsumedMillis"), "timeConsumedMillis"),
        "memory_consumed_bytes": _optional_nonnegative_int(raw.get("memoryConsumedBytes"), "memoryConsumedBytes"),
        "passed_test_count": _optional_nonnegative_int(raw.get("passedTestCount"), "passedTestCount"),
        "participant_type": author.get("participantType") if isinstance(author.get("participantType"), str) else None,
        "attribution_status": attribution,
        "author_members_raw": members,
        "raw_problem": problem,
        "last_checked_at": checked_at,
    }


def reconcile_unresolved_submissions(account_id):
    """Resolve foreign keys for submissions whose problems were added to the catalog later.

    Does not commit: the caller manages the transaction.
    """
    lookup = codeforces_problem_lookup()
    unresolved = db.session.execute(
        db.select(CodeforcesSubmission).where(
            CodeforcesSubmission.codeforces_account_id == account_id,
            CodeforcesSubmission.problem_id.is_(None),
            CodeforcesSubmission.cf_problem_external_id.is_not(None),
        )
    ).scalars()
    count = 0
    for row in unresolved:
        pk = lookup.get(row.cf_problem_external_id)
        if pk is not None:
            row.problem_id = pk
            count += 1
    return count
