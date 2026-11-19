from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from recommendations.scoring import (
    difficulty_fit, topic_priority, retry_relevance, rank_candidates,
    normalized_weights, DEFAULT_WEIGHTS,
)
from recommendations.candidate_generator import (
    canonical_problem_url, eligible_candidates, build_history, select_rating_window,
)

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def problem(pid, rating=1200, tags=None, platform="CODEFORCES"):
    return SimpleNamespace(id=pid, platform=platform, external_id=f"1900:{chr(64+pid)}",
        contest_id="1900", problem_index=chr(64+pid), title=f"P{pid}",
        url=f"https://codeforces.com/problemset/problem/1900/{chr(64+pid)}",
        difficulty_raw={"rating": rating} if rating is not None else None,
        tags_raw=tags or ["greedy"] , codeforces_rating=rating)


def test_valid_score_weights():
    assert normalized_weights(DEFAULT_WEIGHTS) == DEFAULT_WEIGHTS


def test_difficulty_target_fit():
    assert difficulty_fit(1200, 1200, 400) > difficulty_fit(1800, 1200, 400)


def test_unknown_mastery_explores():
    assert topic_priority(["greedy"], {}) == 0.65
    assert topic_priority(["greedy"], {"greedy": {"mastery_score": .9, "confidence": 1}}) < 0.65


def test_retries_gain_relevance_after_spacing():
    recent = retry_relevance("retry", 1, NOW - timedelta(hours=1), NOW)
    later = retry_relevance("retry", 1, NOW - timedelta(days=30), NOW)
    assert later > recent


def test_canonical_only():
    assert canonical_problem_url(problem(1))
    broken = problem(2)
    broken.url = "https://example.com/problemset/problem/1900/B"
    assert canonical_problem_url(broken) is None
    unrelated = problem(3, platform="LEETCODE")
    assert canonical_problem_url(unrelated) is None


def test_new_retry_and_pending():
    items = [problem(1), problem(2), problem(3), problem(4), problem(5)]
    histories = {
        2: {"attempted": True, "solved": False, "failures": 2, "pending": False, "provisional": False, "last_attempted_at": NOW},
        3: {"attempted": True, "solved": True, "failures": 0, "pending": False, "provisional": False, "last_attempted_at": NOW},
        4: {"attempted": True, "solved": False, "failures": 0, "pending": True, "provisional": False, "last_attempted_at": NOW},
        5: {"attempted": True, "solved": False, "failures": 1, "pending": False, "provisional": True, "last_attempted_at": NOW},
    }
    assert [x["problem_id"] for x in eligible_candidates(items, histories, {}, mode="new")[0]] == [1]
    assert [x["problem_id"] for x in eligible_candidates(items, histories, {}, mode="retry")[0]] == [2]
    assert [x["problem_id"] for x in eligible_candidates(items, histories, {}, mode="mixed")[0]] == [1, 2]


def test_unresolved_final_ok_excluded_by_external_identity():
    account = 3
    official = SimpleNamespace(codeforces_account_id=account, attribution_status="INDIVIDUAL",
        problem_id=None, cf_problem_external_id="1900:A", verdict="OK", testset="TESTS", submitted_at=NOW)
    ids, external = build_history([], [official], account_id=account)
    assert eligible_candidates([problem(1)], ids, external, mode="new")[0] == []


def test_rated_and_unrated_pools_separate():
    rated, unrated = eligible_candidates([problem(1), problem(2, rating=None)], {}, {}, mode="new")
    assert len(rated) == len(unrated) == 1
    assert rated[0]["rating"] == 1200 and unrated[0]["rating"] is None


def test_widen_without_arbitrary_jump():
    candidates = [{"rating": 1800, "external_id": "A"}, {"rating": 1300, "external_id": "B"}]
    subset, window = select_rating_window(candidates, target=1000, required=2, profile="cold_start")
    assert len(subset) == 1 and subset[0]["rating"] == 1300
    assert window == 600


def test_deterministic_rank_and_diversity():
    items = [
        {"problem_id": i, "external_id": f"1900:{i}", "rating": 1200,
         "tags": ("greedy",) if i < 3 else ("dp",), "candidate_type": "new",
         "official_failure_count": 0, "last_attempted_at": None} for i in [1,2,3]
    ]
    x = rank_candidates(items, target=1200, window=400, mastery={}, weights=DEFAULT_WEIGHTS, limit=3, as_of=NOW)
    y = rank_candidates(list(reversed(items)), target=1200, window=400, mastery={}, weights=DEFAULT_WEIGHTS, limit=3, as_of=NOW)
    assert [a["problem_id"] for a in x] == [a["problem_id"] for a in y]
    assert x[0]["problem_id"] == 1
    assert x[1]["problem_id"] == 3  # Encourage topic diversity.
