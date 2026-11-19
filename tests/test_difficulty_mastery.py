"""Pure skill mathematics: no Flask or network required."""
from datetime import datetime, timedelta, timezone

from analytics.difficulty import ProblemEvidence, estimate_difficulty_readiness
from analytics.mastery_math import derive_topic_mastery

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def ev(pid, *, rating=800, tags=("dp",), solved=True, failures=0, age=1):
    return ProblemEvidence(pid, tuple(tags), rating, solved, failures, NOW - timedelta(days=age))


def test_successful_1800_history_yields_higher_readiness_than_800():
    low = [ev(i, rating=800) for i in range(3)]
    high = [ev(i, rating=1800) for i in range(3)]
    assert estimate_difficulty_readiness(low, as_of=NOW)["readiness_rating"] == 800
    assert estimate_difficulty_readiness(high, as_of=NOW)["readiness_rating"] == 1800


def test_solved_high_rated_topics_have_stronger_weighted_mastery():
    low = derive_topic_mastery([ev(i, rating=800) for i in range(3)], as_of=NOW)[0]
    high = derive_topic_mastery([ev(i, rating=1800) for i in range(3)], as_of=NOW)[0]
    assert high["mastery_score"] > low["mastery_score"]
    assert high["mean_rated_difficulty"] == 1800


def test_distinct_problems_contribute_to_each_tag_once():
    rows = derive_topic_mastery([
        ev(1, tags=("dp", "math", "dp")),
        ev(2, tags=("math",), solved=False, failures=2),
    ], as_of=NOW)
    d = {x["tag"]: x for x in rows}
    assert d["dp"]["attempted_problems"] == 1
    assert d["math"]["attempted_problems"] == 2
    assert d["math"]["solved_problems"] == 1


def test_pending_only_is_unknown_not_zero():
    rows = derive_topic_mastery([ev(1, solved=False, failures=0)], as_of=NOW)
    assert rows[0]["attempted_problems"] == 1
    assert rows[0]["decided_problems"] == 0
    assert rows[0]["mastery_score"] is None
    assert rows[0]["confidence"] == 0.0
    assert estimate_difficulty_readiness([ev(1, solved=False, failures=0)], as_of=NOW)["readiness_rating"] is None


def test_unrated_counts_for_topic_but_not_difficulty_readiness():
    rows = [ev(1, rating=None), ev(2, rating=None), ev(3, rating=None)]
    result = derive_topic_mastery(rows, as_of=NOW)[0]
    assert result["attempted_problems"] == 3
    assert result["rated_decided_problems"] == 0
    assert result["mastery_score"] is not None
    assert estimate_difficulty_readiness(rows, as_of=NOW)["readiness_rating"] is None


def test_old_evidence_reduces_confidence():
    recent = derive_topic_mastery([ev(i, age=1) for i in range(5)], as_of=NOW)[0]
    old = derive_topic_mastery([ev(i, age=1000) for i in range(5)], as_of=NOW)[0]
    assert recent["confidence"] > old["confidence"]


def test_unexposed_tag_is_not_assigned_zero():
    tags = derive_topic_mastery([ev(1, tags=("greedy",))], as_of=NOW)
    assert "dp" not in {row["tag"] for row in tags}


def test_failing_at_higher_band_does_not_fake_readiness():
    rows = ([ev(i, rating=800) for i in range(3)] +
            [ev(10+i, rating=1800, solved=False, failures=1) for i in range(5)])
    result = estimate_difficulty_readiness(rows, as_of=NOW)
    assert result["readiness_rating"] == 800
