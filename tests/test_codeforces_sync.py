"""Offline Step 3 tests. Run: python -m pytest test_codeforces_sync.py -q"""

import pytest
from sqlalchemy.exc import StatementError
from flask import Flask

from database.db import db
from models.problem import Problem
from problem_stats.codeforces import CodeforcesCatalogError, fetch_codeforces_problems
from problem_stats.sync import sync_codeforces_problems


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
        CODEFORCES_TIMEOUT_SECONDS=5,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()  # Isolated test database only; production uses migrations.
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def api_payload():
    return {
        "status": "OK",
        "result": {
            "problems": [
                {
                    "contestId": 1900, "index": "A", "name": "Cover in Water",
                    "type": "PROGRAMMING", "rating": 800,
                    "tags": ["constructive algorithms", "greedy"],
                },
                {
                    "contestId": 1900, "index": "B", "name": "Laura and Operations",
                    "type": "PROGRAMMING", "tags": ["math"],
                },
                {
                    "problemsetName": "custom-set", "index": "C", "name": "Special",
                    "type": "PROGRAMMING", "tags": [],
                },
            ],
            "problemStatistics": [
                {"contestId": 1900, "index": "A", "solvedCount": 500},
                {"contestId": 1900, "index": "B", "solvedCount": 300},
                {"problemsetName": "custom-set", "index": "C", "solvedCount": 12},
            ],
        },
    }


def patch_cf_api(monkeypatch, payload):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(
        "problem_stats.codeforces.requests.get",
        lambda *args, **kwargs: Response(),
    )


def test_collector_keeps_ids_and_missing_rating(app, api_payload, monkeypatch):
    patch_cf_api(monkeypatch, api_payload)
    result = fetch_codeforces_problems()
    assert [p["external_id"] for p in result] == [
        "1900:A", "1900:B", "custom-set:C"
    ]
    assert result[0]["stats_raw"]["solved_count"] == 500
    assert result[1]["difficulty_raw"] is None
    assert result[2]["contest_id"] is None


def test_second_sync_deduplicates_and_preserves_other_platforms(app, api_payload, monkeypatch):
    patch_cf_api(monkeypatch, api_payload)
    db.session.add(Problem(
        platform="ATCODER", external_id="abc100:a",
        title="Old AtCoder problem", url="https://atcoder.jp/",
    ))
    db.session.commit()
    first = sync_codeforces_problems()
    assert first["inserted"] == 3
    assert first["updated"] == 0

    second = sync_codeforces_problems()
    assert second["inserted"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == 3
    assert db.session.query(Problem).filter_by(platform="CODEFORCES").count() == 3
    assert db.session.query(Problem).filter_by(platform="ATCODER").count() == 1

    api_payload["result"]["problems"][0]["rating"] = 900
    third = sync_codeforces_problems()
    assert third["updated"] == 1
    row = db.session.query(Problem).filter_by(platform="CODEFORCES", external_id="1900:A").one()
    assert row.codeforces_rating == 900


def test_ambiguous_problem_is_skipped(app, api_payload, monkeypatch):
    api_payload["result"]["problems"].append({
        "index": "Q", "name": "No contest or problemset", "type": "PROGRAMMING",
    })
    patch_cf_api(monkeypatch, api_payload)
    result = fetch_codeforces_problems()
    assert len(result) == 3
    assert all(not p["external_id"].startswith("unknown:") for p in result)


def test_sync_rolls_back_when_a_row_is_invalid(app, api_payload, monkeypatch):
    patch_cf_api(monkeypatch, api_payload)
    sync_codeforces_problems()
    before = db.session.query(Problem).filter_by(external_id="1900:A").one().codeforces_rating
    # Non-JSON-serializable tags trigger an error during the single final commit.
    # Patch the already normalized catalog instead of the parser (which validates tags).
    from problem_stats import sync as sync_module
    original = fetch_codeforces_problems()
    original[0]["difficulty_raw"] = {"rating": 900}
    original[1]["tags_raw"] = {"not_json_serializable"}
    monkeypatch.setattr(sync_module, "fetch_codeforces_problems", lambda: original)

    with pytest.raises((StatementError, TypeError)):
        sync_codeforces_problems()

    db.session.expire_all()
    row = db.session.query(Problem).filter_by(external_id="1900:A").one()
    assert row.codeforces_rating == before


def test_failed_api_response_is_rejected(app, monkeypatch):
    patch_cf_api(monkeypatch, {"status": "FAILED", "comment": "rate limited"})
    with pytest.raises(CodeforcesCatalogError):
        fetch_codeforces_problems()
