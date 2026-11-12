"""Pure unit tests; no Codeforces network access or Flask database required."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from analytics.aggregation import aggregate_submissions, classify_official_submission

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def row(problem, sec, verdict, testset="TESTS", attribution="INDIVIDUAL", checked=100):
    return SimpleNamespace(
        problem_id=problem, submitted_at=BASE + timedelta(seconds=sec),
        last_checked_at=BASE + timedelta(seconds=checked),
        verdict=verdict, testset=testset, attribution_status=attribution,
    )


def test_three_failures_then_ok_and_independent_problem():
    rows = [row(10, 1, "WRONG_ANSWER"), row(10, 2, "WRONG_ANSWER"),
            row(10, 3, "WRONG_ANSWER"), row(10, 4, "OK"),
            row(11, 5, "OK", testset="PRETESTS"),
            row(12, 6, None),
            row(13, 7, "OK", attribution="TEAM"),
            row(None, 8, "OK"),
            row(14, 9, "OK", attribution="UNKNOWN")]
    result = aggregate_submissions(rows)
    assert set(result) == {10, 11, 12}
    solved = result[10]
    assert solved.official_submission_count == 4
    assert solved.official_failure_count == 3
    assert solved.official_final_ok_count == 1
    assert solved.is_solved is True
    assert solved.first_solved_at == BASE + timedelta(seconds=4)
    assert result[11].official_provisional_ok_count == 1
    assert result[11].is_solved is False
    assert result[12].official_pending_count == 1
    assert result[12].is_solved is False


def test_rejudging_and_order_independent():
    old = [row(10, 1, "OK"), row(10, 2, "WRONG_ANSWER")]
    first = aggregate_submissions(old)[10]
    assert first.is_solved
    changed = [row(10, 1, "WRONG_ANSWER"), row(10, 2, "WRONG_ANSWER")]
    second = aggregate_submissions(reversed(changed))[10]
    assert not second.is_solved
    assert second.official_failure_count == 2
    assert second.first_attempted_at == BASE + timedelta(seconds=1)
    assert second.last_submitted_at == BASE + timedelta(seconds=2)
    assert second.progress_updated_at == BASE + timedelta(seconds=100)


def test_pretests_failure_and_unknown_verdict():
    assert classify_official_submission("WRONG_ANSWER", "PRETESTS") == "FAILURE"
    assert classify_official_submission("OK", "PRETESTS") == "PROVISIONAL_OK"
    assert classify_official_submission("OK", None) == "PROVISIONAL_OK"
    assert classify_official_submission("TESTING", "TESTS") == "PENDING"
    assert classify_official_submission("SKIPPED", "TESTS") == "OTHER"
