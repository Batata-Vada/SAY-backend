"""Run inside SAY's real WSL virtualenv: requires Flask and SQLAlchemy.

Temporary SQLite DB, no Codeforces network requests, no production DB changes.
"""
from datetime import datetime, timezone
from importlib import import_module

import pytest


@pytest.fixture
def say_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-recommendation-secret-key-not-production")
    main = import_module("main")
    app = main.create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "RECOMMENDATION_WEIGHTS": {"difficulty": .4, "topic": .35, "recency": .15, "diversity": .1},
        "RECOMMENDATION_DEFAULT_RATING": 1000,
        "RECOMMENDATION_CANDIDATE_POOL_CAP": 300,
    })
    with app.app_context():
        from database.db import db
        db.create_all()  # Allowed ONLY in isolated ephemeral tests.
        yield app
        db.session.remove()
        db.drop_all()


def create_user_and_token(name):
    from database.db import db
    from models.users import User
    from models.session import Session
    from middleware.auth import issue_session_token, token_digest
    user = User(name=name, email=f"{name}@example.test", password="test-hash", privilege="user")
    db.session.add(user)
    db.session.flush()
    token = issue_session_token(user.uid)
    db.session.add(Session(uid=user.uid, token=token_digest(token)))
    db.session.commit()
    return user.uid, {"Authorization": f"Bearer {token}"}


def make_problem(i, rating=1000, tags=None):
    from models.problem import Problem
    return Problem(
        platform="CODEFORCES", external_id=f"1900:{chr(65+i)}",
        title=f"Practice problem {i}", contest_id="1900", problem_index=chr(65+i),
        url=f"https://codeforces.com/problemset/problem/1900/{chr(65+i)}",
        difficulty_raw={"rating": rating} if rating else None,
        tags_raw=tags or ["greedy" if i % 2 else "dp"],
        stats_raw={}, metadata_raw={},
    )


def link(uid, handle):
    from database.db import db
    from models.codeforces_account import CodeforcesAccount
    acc = CodeforcesAccount(uid=uid, handle=handle, ownership_verified=False,
                             sync_status="PENDING", last_synced_at=None)
    db.session.add(acc)
    db.session.commit()
    return acc.id


def official(acc_id, sid, p, verdict, testset="TESTS", attribution="INDIVIDUAL", missing_fk=False):
    from database.db import db
    from models.codeforces_submission import CodeforcesSubmission
    row = CodeforcesSubmission(
        codeforces_account_id=acc_id, cf_submission_id=sid,
        problem_id=None if missing_fk else p.id,
        cf_problem_external_id=p.external_id,
        cf_contest_id="1900", cf_problem_index=p.problem_index,
        verdict=verdict, testset=testset, programming_language="Python 3",
        submitted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        attribution_status=attribution, author_members_raw=[], raw_problem={},
    )
    db.session.add(row)
    db.session.commit()


def test_cold_start_and_log_generation(say_app):
    from database.db import db
    from models.recommendation_log import RecommendationLog
    with say_app.app_context():
        uid, headers = create_user_and_token("fresh")
        for i in range(8):
            db.session.add(make_problem(i))
        db.session.commit()
    client = say_app.test_client()
    result = client.post("/api/me/recommendations", headers=headers, json={"mode": "new", "limit": 4})
    assert result.status_code == 200, result.get_json()
    body = result.get_json()
    assert body["profile"] == "cold_start"
    assert body["returned"] == 4
    assert all(x["candidate_type"] == "new" for x in body["recommendations"])
    assert all(x["ranking_strategy"] == "rated" for x in body["recommendations"])
    with say_app.app_context():
        assert db.session.query(RecommendationLog).filter_by(uid=uid).count() == 4
    history = client.get("/api/me/recommendations/history", headers=headers)
    assert history.status_code == 200 and history.get_json()["total"] == 4


def test_official_final_solve_pending_and_team(say_app):
    from database.db import db
    with say_app.app_context():
        uid, headers = create_user_and_token("solves")
        account = link(uid, "test-handle")
        items = [make_problem(i) for i in range(6)]
        db.session.add_all(items)
        db.session.commit()
        official(account, 101, items[0], "OK", missing_fk=True)  # unresolved FK, stable external ID
        official(account, 102, items[1], "WRONG_ANSWER")
        official(account, 103, items[2], None)
        official(account, 104, items[3], "OK", testset="PRETESTS")
        official(account, 105, items[4], "OK", attribution="TEAM")
    client = say_app.test_client()
    new = client.post("/api/me/recommendations", headers=headers, json={"mode": "new", "limit": 10})
    assert new.status_code == 200, new.get_json()
    new_ids = {x["external_id"] for x in new.get_json()["recommendations"]}
    assert "1900:A" not in new_ids  # Final solve excluded despite unresolved FK.
    assert "1900:B" not in new_ids  # Failed attempt is a retry, not new.
    assert "1900:C" not in new_ids  # Pending is neither a retry nor new.
    assert "1900:D" not in new_ids  # PRETESTS OK is provisional.
    assert "1900:E" in new_ids  # Team result cannot imply personal success.
    retry = client.post("/api/me/recommendations", headers=headers, json={"mode": "retry", "limit": 10})
    assert retry.status_code == 200
    assert [x["external_id"] for x in retry.get_json()["recommendations"]] == ["1900:B"]


def test_two_users_have_different_eligible_lists(say_app):
    from database.db import db
    with say_app.app_context():
        uid_a, headers_a = create_user_and_token("alpha")
        uid_b, headers_b = create_user_and_token("beta")
        account_a = link(uid_a, "alpha-codeforces")
        account_b = link(uid_b, "beta-codeforces")
        p = [make_problem(i) for i in range(6)]
        db.session.add_all(p)
        db.session.commit()
        for i in range(3):
            official(account_a, 1000+i, p[i], "OK")
        for i in range(3, 6):
            official(account_b, 1000+i, p[i], "OK")
    client = say_app.test_client()
    ra = client.post("/api/me/recommendations", headers=headers_a, json={"mode": "new", "limit": 3})
    rb = client.post("/api/me/recommendations", headers=headers_b, json={"mode": "new", "limit": 3})
    assert ra.status_code == rb.status_code == 200
    a = {x["external_id"] for x in ra.get_json()["recommendations"]}
    b = {x["external_id"] for x in rb.get_json()["recommendations"]}
    assert a != b and not a.intersection(b)
    history_a = client.get("/api/me/recommendations/history", headers=headers_a).get_json()
    history_b = client.get("/api/me/recommendations/history", headers=headers_b).get_json()
    assert history_a["total"] == history_b["total"] == 3


def test_validation_and_auth(say_app):
    with say_app.app_context():
        _, headers = create_user_and_token("validation")
    client = say_app.test_client()
    assert client.post("/api/me/recommendations", json={"mode": "new"}).status_code == 401
    assert client.post("/api/me/recommendations", headers=headers, json={"mode": "bad"}).status_code == 400
    assert client.post("/api/me/recommendations", headers=headers, json={"limit": 1000}).status_code == 400
    assert client.post("/api/me/recommendations", headers=headers, json={"limit": True}).status_code == 400
    assert client.get("/api/me/recommendations/history?limit=-1", headers=headers).status_code == 400
