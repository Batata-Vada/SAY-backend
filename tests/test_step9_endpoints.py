"""Phase 1 Step 9 integration tests. Run in SAY's .venv, not production DB."""
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("SECRET_KEY", "test-step9-dev-secret-not-for-production-very-long")


@pytest.fixture
def env(tmp_path):
    from main import create_app
    from database.db import db
    from middleware.auth import issue_session_token, token_digest
    from models.users import User
    from models.session import Session
    from models.codeforces_account import CodeforcesAccount

    db_path = tmp_path / "step9-test.db"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-step9-dev-secret-not-for-production-very-long",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "RECOMMENDATION_WEIGHTS": {"difficulty": .4, "topic": .35, "recency": .15, "diversity": .1},
        "RECOMMENDATION_DEFAULT_RATING": 1000,
        "RECOMMENDATION_CANDIDATE_POOL_CAP": 100,
    })
    with app.app_context():
        db.create_all()  # ONLY on disposable isolated test DB, never in main.py
        users = [
            User(name="sid_test", email="sid@example.test", password="not-used", privilege="user"),
            User(name="other", email="other@example.test", password="not-used", privilege="user"),
        ]
        db.session.add_all(users)
        db.session.flush()
        accounts = [
            CodeforcesAccount(uid=users[0].uid, handle="macyapp", sync_status="PENDING",
                              ownership_verified=False, registration_time_seconds=123),
            CodeforcesAccount(uid=users[1].uid, handle="anotheruser", sync_status="PENDING",
                              ownership_verified=False, registration_time_seconds=124),
        ]
        db.session.add_all(accounts)
        db.session.flush()
        tokens = {}
        for user in users:
            token = issue_session_token(user.uid)
            tokens[user.uid] = token
            db.session.add(Session(uid=user.uid, token=token_digest(token)))
        db.session.commit()
        ids = (users[0].uid, users[1].uid, accounts[0].id, accounts[1].id)
    yield app, app.test_client(), tokens, ids
    with app.app_context():
        db.session.remove()
        db.drop_all()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_authentication_and_user_isolation(env):
    app, client, tokens, (uid1, uid2, a1, a2) = env
    assert client.get("/api/codeforces/sync").status_code == 401
    assert client.post("/api/codeforces/sync", json={}).status_code == 401
    assert client.get("/api/codeforces/submissions").status_code == 401
    assert client.get("/api/recommendations").status_code == 401

    r = client.get("/api/codeforces/sync", headers=auth(tokens[uid1]))
    assert r.status_code == 200
    assert r.json["account"]["id"] == a1
    r2 = client.get("/api/codeforces/sync", headers=auth(tokens[uid2]))
    assert r2.json["account"]["id"] == a2


def test_post_sync_duplicate_poll_and_worker(env, monkeypatch):
    from database.db import db
    from models.codeforces_sync_request import CodeforcesSyncRequest
    from codeforces.sync_queue import process_one_sync_request
    app, client, tokens, (uid1, uid2, a1, a2) = env
    headers = auth(tokens[uid1])
    first = client.post("/api/codeforces/sync", json={"full": False}, headers=headers)
    assert first.status_code == 202
    assert first.json["job"]["status"] == "QUEUED"
    assert first.headers["Location"] == "/api/codeforces/sync"
    assert client.post("/api/codeforces/sync", json={}, headers=headers).status_code == 409
    assert client.post("/api/codeforces/sync", json={"full": "yes"}, headers=headers).status_code == 400
    assert client.get("/api/codeforces/sync", headers=headers).json["job"]["status"] == "QUEUED"
    assert client.get("/api/codeforces/sync", headers=auth(tokens[uid2])).json["job"] is None

    monkeypatch.setattr("codeforces.sync_queue.sync_codeforces_submissions",
                        lambda account_id, *, full: {"account_id": account_id, "inserted": 1})
    monkeypatch.setattr("codeforces.sync_queue.rebuild_user_progress",
                        lambda uid: {"distinct_attempted_problems": 1, "distinct_solved_problems": 1})
    monkeypatch.setattr("codeforces.sync_queue.rebuild_user_skills",
                        lambda uid: {"model_version": "cf-skills-v1", "readiness_rating": 1000})
    with app.app_context():
        assert process_one_sync_request()["status"] == "SUCCEEDED"
        assert process_one_sync_request() is None
        row = db.session.get(CodeforcesSyncRequest, first.json["job"]["id"])
        assert row.status == "SUCCEEDED"
        assert row.result_raw["progress"]["distinct_solved_problems"] == 1
    assert client.get("/api/codeforces/sync", headers=headers).json["job"]["status"] == "SUCCEEDED"
    assert client.post("/api/codeforces/sync", json={"full": True}, headers=headers).status_code == 202


def test_worker_failure_releases_queue(env, monkeypatch):
    from codeforces.sync_queue import process_one_sync_request
    app, client, tokens, (uid1, _uid2, _a1, _a2) = env
    h = auth(tokens[uid1])
    assert client.post("/api/codeforces/sync", headers=h, json={}).status_code == 202
    def fail(*args, **kwargs):
        raise RuntimeError("Test simulated Codeforces error")
    monkeypatch.setattr("codeforces.sync_queue.sync_codeforces_submissions", fail)
    with app.app_context():
        assert process_one_sync_request()["status"] == "FAILED"
    assert client.get("/api/codeforces/sync", headers=h).json["job"]["status"] == "FAILED"
    assert client.post("/api/codeforces/sync", headers=h, json={}).status_code == 202


def test_submission_pagination_filters_only_active_user(env):
    from database.db import db
    from models.codeforces_submission import CodeforcesSubmission
    app, client, tokens, (uid1, uid2, a1, a2) = env
    with app.app_context():
        for account_id, sid, verdict in [(a1, 101, "OK"), (a1, 102, "WRONG_ANSWER"), (a2, 201, "OK")]:
            db.session.add(CodeforcesSubmission(
                codeforces_account_id=account_id, cf_submission_id=sid,
                verdict=verdict, testset="TESTS", attribution_status="INDIVIDUAL",
                submitted_at=datetime.now(timezone.utc), last_checked_at=datetime.now(timezone.utc),
                author_members_raw=[], raw_problem={},
            ))
        db.session.commit()
    h = auth(tokens[uid1])
    response = client.get("/api/codeforces/submissions?limit=1&offset=0", headers=h)
    assert response.status_code == 200
    assert response.json["total"] == 2
    assert response.json["pagination"]["returned"] == 1
    ids = [x["cf_submission_id"] for x in response.json["submissions"]]
    assert not set(ids) & {201}
    ok = client.get("/api/codeforces/submissions?verdict=OK", headers=h)
    assert ok.json["total"] == 1
    assert ok.json["submissions"][0]["is_final_individual_solve"] is True
    assert client.get("/api/codeforces/submissions?limit=-1", headers=h).status_code == 400
    other = client.get("/api/codeforces/submissions", headers=auth(tokens[uid2]))
    assert other.json["total"] == 1
    assert other.json["submissions"][0]["cf_submission_id"] == 201


def test_get_recommendations_reuses_existing_logged_service(env):
    from database.db import db
    from models.problem import Problem
    from models.recommendation_log import RecommendationLog
    app, client, tokens, (uid1, uid2, a1, a2) = env
    with app.app_context():
        db.session.add(Problem(
            platform="CODEFORCES", external_id="1900:A", title="Practice example",
            url="https://codeforces.com/problemset/problem/1900/A",
            contest_id="1900", problem_index="A",
            difficulty_raw={"rating": 1000}, tags_raw=["implementation"],
            stats_raw={}, metadata_raw={},
        ))
        db.session.commit()
    r = client.get("/api/recommendations?limit=5&mode=new", headers=auth(tokens[uid1]))
    assert r.status_code == 200, r.json
    assert r.json["model"] == "cf-recommend-v1"
    assert len(r.json["recommendations"]) == 1
    assert "reason" in r.json["recommendations"][0]
    assert "no-store" in r.headers["Cache-Control"]
    with app.app_context():
        log = db.session.execute(db.select(RecommendationLog)).scalars().all()
        assert len(log) == 1 and log[0].uid == uid1
    assert client.get("/api/recommendations?mode=unknown", headers=auth(tokens[uid1])).status_code == 400
    assert client.get("/api/recommendations?limit=0", headers=auth(tokens[uid1])).status_code == 400
