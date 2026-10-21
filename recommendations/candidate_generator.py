"""Generate safe candidates from the existing canonical Codeforces catalog.

No live URL verification: accepted URLs follow the canonical problem URL shape.
Catalog can contain deleted/inaccessible tasks, so this is a best-effort filter.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from analytics.aggregation import FAILURE_VERDICTS, as_utc
from analytics.difficulty import valid_rating

INDEX = re.compile(r"[A-Za-z0-9]+\Z")
PATH = re.compile(r"/(?:problemset/problem|contest/\d+/problem)/\d+/[A-Za-z0-9]+\Z")
CORE_TOPICS = frozenset({"implementation", "math", "greedy", "brute force", "sortings", "strings", "binary search", "dp", "graphs"})


def normalized_tags(raw):
    if not isinstance(raw, list):
        return ()
    return tuple(sorted({t.strip().lower() for t in raw if isinstance(t, str) and t.strip()}))


def canonical_problem_url(problem):
    """Only return valid, direct Codeforces contest/problemset links."""
    if problem.platform != "CODEFORCES" or not isinstance(problem.url, str):
        return None
    contest = problem.contest_id
    index = problem.problem_index
    if not isinstance(contest, str) or not contest.isdigit() or int(contest) <= 0:
        return None
    if not isinstance(index, str) or not INDEX.fullmatch(index):
        return None
    if problem.external_id != f"{int(contest)}:{index}":
        return None
    try:
        parsed = urlsplit(problem.url)
        invalid_authority = (parsed.port is not None or parsed.username is not None
                             or parsed.password is not None)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != "codeforces.com" or
            invalid_authority or parsed.query or parsed.fragment or
            not PATH.fullmatch(parsed.path)):
        return None
    allowed = {
        f"/problemset/problem/{int(contest)}/{index}",
        f"/contest/{int(contest)}/problem/{index}",
    }
    if parsed.path not in allowed:
        return None
    return problem.url


def build_history(progress_rows, submission_rows, *, account_id):
    """Merge progress and official raw rows for fail-closed solved exclusion.

    Unresolved submission problem IDs can still match catalog external IDs.
    Do not treat team / uncertain attribution as an individual solve.
    """
    by_id, by_external = {}, {}

    def state(mapping, key):
        if key is None:
            return None
        return mapping.setdefault(key, {
            "attempted": False, "solved": False, "failures": 0,
            "pending": False, "provisional": False, "last_attempted_at": None,
        })

    for row in progress_rows:
        if row.source_account_id != account_id:
            continue
        s = state(by_id, row.problem_id)
        s["attempted"] = True
        s["solved"] |= bool(row.is_solved)
        s["failures"] = max(s["failures"], row.official_failure_count)
        s["pending"] |= row.official_pending_count > 0
        s["provisional"] |= row.official_provisional_ok_count > 0
        s["last_attempted_at"] = as_utc(row.last_submitted_at)

    official_failures_id = {}
    official_failures_external = {}
    for row in submission_rows:
        if row.codeforces_account_id != account_id or row.attribution_status != "INDIVIDUAL":
            continue
        for mapping, key in ((by_id, row.problem_id), (by_external, row.cf_problem_external_id)):
            s = state(mapping, key)
            if s is None:
                continue
            s["attempted"] = True
            s["solved"] |= row.verdict == "OK" and row.testset == "TESTS"
            if row.verdict in FAILURE_VERDICTS:
                counter = official_failures_id if mapping is by_id else official_failures_external
                counter[key] = counter.get(key, 0) + 1
                s["failures"] = max(s["failures"], counter[key])
            s["pending"] |= row.verdict is None or row.verdict == "TESTING"
            s["provisional"] |= row.verdict == "OK" and row.testset != "TESTS"
            t = as_utc(row.submitted_at)
            if s["last_attempted_at"] is None or t > s["last_attempted_at"]:
                s["last_attempted_at"] = t
    return by_id, by_external


def _joined_history(by_id, by_external, problem):
    states = [by_id.get(problem.id), by_external.get(problem.external_id)]
    states = [s for s in states if s is not None]
    if not states:
        return {"attempted": False, "solved": False, "failures": 0, "pending": False, "provisional": False, "last_attempted_at": None}
    last = [s["last_attempted_at"] for s in states if s["last_attempted_at"] is not None]
    return {"attempted": any(s["attempted"] for s in states), "solved": any(s["solved"] for s in states),
            "failures": max(s["failures"] for s in states), "pending": any(s["pending"] for s in states),
            "provisional": any(s["provisional"] for s in states), "last_attempted_at": max(last) if last else None}


def eligible_candidates(problems, by_id, by_external, *, mode):
    """Construct candidate metadata, separate rated and unrated pools."""
    rated, unrated = [], []
    for problem in problems:
        url = canonical_problem_url(problem)
        if url is None:
            continue
        past = _joined_history(by_id, by_external, problem)
        if past["solved"]:
            continue
        if not past["attempted"]:
            kind = "new"
        elif past["failures"] > 0 and not (past["pending"] or past["provisional"]):
            kind = "retry"
        else:
            continue  # Pending and provisional work must not be recommended as new/retry.
        if mode == "new" and kind != "new":
            continue
        if mode == "retry" and kind != "retry":
            continue
        rating = problem.codeforces_rating if valid_rating(problem.codeforces_rating) else None
        candidate = {
            "problem_id": problem.id, "external_id": problem.external_id,
            "title": problem.title, "url": url, "rating": rating,
            "tags": normalized_tags(problem.tags_raw), "candidate_type": kind,
            "official_failure_count": past["failures"], "last_attempted_at": past["last_attempted_at"],
        }
        (rated if rating is not None else unrated).append(candidate)
    return rated, unrated


def select_rating_window(candidates, *, target, required, profile):
    """Gradually relax the practice band; cap wideness per profile."""
    stages = {
        "cold_start": (200, 400, 600),
        "sparse": (300, 500, 800, 1000),
        "personalized": (200, 400, 600, 1000, 1200),
    }[profile]
    selected = []
    chosen_window = stages[-1]
    for window in stages:
        selected = [c for c in candidates if abs(c["rating"] - target) <= window]
        chosen_window = window
        if len(selected) >= required:
            break
    # Bound candidate pool ordering before expensive diversity-aware reranking.
    selected.sort(key=lambda c: (abs(c["rating"] - target), c["external_id"]))
    return selected, chosen_window
