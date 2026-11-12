"""Integration tests against isolated temporary SQLite; external API never called."""
from datetime import datetime, timedelta, timezone
import importlib

import pytest

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "not-a-production-secret-tests-only")
    # Global main app may be imported before fixture, but does not create tables.
    main = importlib.import_module("main")
    from database.db import db
    app = main.create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.db"),
        "TESTING": True,
        "SECRET_KEY": "not-a-production-secret-tests-only",
        "CORS_ORIGINS": ["http://localhost:5173"],
    })
    with app.app_context():
        # Allowed ONLY for a fresh, disposable test database.
        db.create_all()
        yield app, db
        db.session.remove()
        db.drop_all()


def setup_user_account(db, *, uid=None, handle="testing_user", active=True):
    from models.users import User
    from models.codeforces_account import CodeforcesAccount
    user = User(name=handle, email=f"{handle}@example.test", password="not-used", privilege="user")
    db.session.add(user)
    db.session.flush()
    acc = CodeforcesAccount(
        uid=user.uid, handle=handle, linked_at=BASE,
        unlinked_at=None if active else BASE + timedelta(seconds=1),
        ownership_verified=False, sync_status="SUCCEEDED", last_synced_at=BASE + timedelta(hours=1),
    )
    db.session.add(acc)
    db.session.flush()
    return user, acc


def add_problem(db, *, ext="1900:A", platform="CODEFORCES"):
    from models.problem import Problem
    p = Problem(platform=platform, external_id=ext, title=f"Problem {ext}",
                url="https://codeforces.com/problemset", difficulty_raw={"rating": 900},
                tags_raw=["dp"], stats_raw={}, metadata_raw={},
                first_seen_at=BASE, last_seen_at=BASE, last_fetched_at=BASE)
    db.session.add(p)
    db.session.flush()
    return p


def add_submission(db, acc, p, sid, sec, verdict, *, testset="TESTS", attribution="INDIVIDUAL"):
    from models.codeforces_submission import CodeforcesSubmission
    row = CodeforcesSubmission(
        codeforces_account_id=acc.id, cf_submission_id=sid,
        problem_id=p.id if p is not None else None,
        cf_problem_external_id=p.external_id if p else "other:A",
        verdict=verdict, testset=testset, programming_language="GNU C++20",
        submitted_at=BASE + timedelta(seconds=sec),
        attribution_status=attribution, author_members_raw=[], raw_problem={},
        last_checked_at=BASE + timedelta(minutes=2),
    )
    db.session.add(row)
    return row


def test_rebuild_and_rejudging(env):
    app, db = env
    from analytics.progress import rebuild_user_progress, read_user_progress
    from models.user_problem_progress import UserProblemProgress
    from models.codeforces_submission import CodeforcesSubmission
    with app.app_context():
        user, acc = setup_user_account(db)
        p = add_problem(db)
        for sid in range(1, 4):
            add_submission(db, acc, p, sid, sid, "WRONG_ANSWER")
        ok = add_submission(db, acc, p, 4, 4, "OK")
        other = add_problem(db, ext="1900:B")
        add_submission(db, acc, other, 5, 5, "OK", testset="PRETESTS")
        add_submission(db, acc, other, 6, 6, None)
        add_submission(db, acc, other, 7, 7, "OK", attribution="TEAM")
        add_submission(db, acc, None, 8, 8, "OK")
        db.session.commit()

        summary = rebuild_user_progress(user.uid)
        assert summary["distinct_attempted_problems"] == 2
        assert summary["distinct_solved_problems"] == 1
        assert summary["qualifying_official_submissions"] == 6
        assert summary["official_failures"] == 3
        first = read_user_progress(user.uid)
        assert not first["needs_rebuild"]
        assert first["distinct_attempted_problems"] == 2
        p1 = db.session.get(UserProblemProgress, (user.uid, p.id))
        saved = (p1.official_submission_count, p1.first_solved_at, p1.progress_updated_at)
        rebuild_user_progress(user.uid)
        p1 = db.session.get(UserProblemProgress, (user.uid, p.id))
        assert saved == (p1.official_submission_count, p1.first_solved_at, p1.progress_updated_at)

        row = db.session.get(CodeforcesSubmission, ok.id)
        row.verdict = "WRONG_ANSWER"
        row.last_checked_at = BASE + timedelta(minutes=3)
        db.session.commit()
        assert read_user_progress(user.uid)["needs_rebuild"] is True
        rebuild_user_progress(user.uid)
        assert read_user_progress(user.uid)["distinct_solved_problems"] == 0
        p1 = db.session.get(UserProblemProgress, (user.uid, p.id))
        assert p1.official_failure_count == 4
        assert p1.first_solved_at is None


def test_relink_isolation_and_authentication(env):
    app, db = env
    from analytics.progress import rebuild_user_progress, read_user_progress
    from middleware.auth import issue_session_token, token_digest
    from models.session import Session
    from models.user_problem_progress import UserProblemProgress
    with app.app_context():
        user, old_account = setup_user_account(db, handle="user_old")
        p = add_problem(db)
        add_submission(db, old_account, p, 20, 1, "OK")
        db.session.commit()
        rebuild_user_progress(user.uid)
        old_account.unlinked_at = BASE + timedelta(days=1)
        newer = setup_second_account(db, user.uid)
        db.session.commit()
        assert read_user_progress(user.uid)["distinct_attempted_problems"] == 0
        assert read_user_progress(user.uid)["codeforces_account_id"] == newer.id
        rebuild_user_progress(user.uid)
        assert db.session.get(UserProblemProgress, (user.uid, p.id)) is None

        token = issue_session_token(user.uid)
        db.session.add(Session(uid=user.uid, token=token_digest(token)))
        db.session.commit()
        client = app.test_client()
        assert client.get("/api/me/progress").status_code == 401
        response = client.get("/api/me/progress", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json["distinct_solved_problems"] == 0


def setup_second_account(db, uid):
    from models.codeforces_account import CodeforcesAccount
    newer = CodeforcesAccount(uid=uid, handle="user_new", linked_at=BASE + timedelta(days=1),
                              ownership_verified=False, sync_status="PENDING")
    db.session.add(newer)
    db.session.flush()
    return newer
