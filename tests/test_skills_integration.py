"""Flask/database integration tests. Run in the project's WSL virtualenv."""
import os
from datetime import datetime, timedelta, timezone

import pytest

# main.py builds an application at import time; give it a harmless test secret.
os.environ["SECRET_KEY"] = "step7-test-secret-only"

from main import create_app  # noqa: E402
from database.db import db  # noqa: E402
from models.users import User  # noqa: E402
from models.session import Session  # noqa: E402
from models.problem import Problem  # noqa: E402
from models.codeforces_account import CodeforcesAccount  # noqa: E402
from models.codeforces_submission import CodeforcesSubmission  # noqa: E402
from models.user_problem_progress import UserProblemProgress  # noqa: E402
from models.user_topic_mastery import UserDifficultyReadiness  # noqa: E402
from analytics.mastery import rebuild_user_skills, read_user_skills, SkillEstimateError  # noqa: E402
from middleware.auth import issue_session_token, token_digest  # noqa: E402

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "step7-test-secret-only",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'skill_test.db'}",
        "CORS_ORIGINS": ["http://localhost:5173"],
    })
    with app.app_context():
        db.create_all()  # Test-only database, NOT production startup.
        yield app
        db.session.remove()
        db.drop_all()


def seed_user(uid=1, handle="sample"):
    user = User(uid=uid, name=f"student{uid}", email=f"student{uid}@example.com",
                password="not-used", privilege="user")
    db.session.add(user)
    db.session.flush()
    account = CodeforcesAccount(uid=uid, handle=handle, ownership_verified=False,
                                linked_at=NOW - timedelta(days=2), sync_status="SUCCEEDED",
                                last_synced_at=NOW - timedelta(hours=1))
    db.session.add(account)
    db.session.flush()
    return account


def add_problem_progress(uid, account_id, number, rating=1200, tag="dp",
                         solved=True, failure=0, checked=NOW - timedelta(hours=2)):
    problem = Problem(
        platform="CODEFORCES", external_id=f"1999:{number}", title=f"Problem {number}",
        url=f"https://codeforces.com/problemset/problem/1999/{number}",
        difficulty_raw={"rating": rating} if rating is not None else None,
        tags_raw=[tag], stats_raw={}, metadata_raw={},
        first_seen_at=NOW, last_seen_at=NOW, last_fetched_at=NOW,
    )
    db.session.add(problem)
    db.session.flush()
    submitted = NOW - timedelta(days=1)
    db.session.add(CodeforcesSubmission(
        codeforces_account_id=account_id, cf_submission_id=number,
        problem_id=problem.id, submitted_at=submitted,
        verdict="OK" if solved else "WRONG_ANSWER", testset="TESTS",
        attribution_status="INDIVIDUAL", author_members_raw=[{"handle": "sample"}],
        raw_problem={}, last_checked_at=checked,
    ))
    db.session.add(UserProblemProgress(
        uid=uid, problem_id=problem.id, source_account_id=account_id,
        official_submission_count=1, official_failure_count=failure,
        official_final_ok_count=int(solved), official_pending_count=0,
        official_provisional_ok_count=0, official_unclassified_count=0,
        is_solved=solved, first_attempted_at=submitted,
        first_solved_at=submitted if solved else None,
        last_submitted_at=submitted, progress_updated_at=checked,
    ))
    return problem


def test_rebuild_idempotent_and_authenticated_endpoints(app):
    with app.app_context():
        account = seed_user()
        for n in range(1, 4):
            add_problem_progress(1, account.id, n, rating=1800, tag="dp")
        db.session.commit()
        first = rebuild_user_skills(1, as_of=NOW)
        before = read_user_skills(1)
        second = rebuild_user_skills(1, as_of=NOW)
        after = read_user_skills(1)
        assert first["readiness_rating"] == 1800
        assert first == second
        assert before == after
        assert after["topics"][0]["attempted_problems"] == 3
        token = issue_session_token(1)
        db.session.add(Session(uid=1, token=token_digest(token)))
        db.session.commit()

    client = app.test_client()
    assert client.get("/api/me/mastery").status_code == 401
    r = client.get("/api/me/mastery", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["difficulty_readiness"]["readiness_rating"] == 1800
    r = client.get("/api/me/difficulty-readiness", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.get_json()


def test_stale_progress_changes_invalidate_skill_snapshot(app):
    with app.app_context():
        account = seed_user()
        p = add_problem_progress(1, account.id, 1, solved=True)
        db.session.commit()
        rebuild_user_skills(1, as_of=NOW)
        progress = db.session.get(UserProblemProgress, (1, p.id))
        progress.is_solved = False  # As if an aggregate had been rebuilt after rejudge.
        progress.official_final_ok_count = 0
        progress.official_failure_count = 1
        db.session.commit()
        with pytest.raises(SkillEstimateError, match="stale"):
            read_user_skills(1)


def test_account_relink_prevents_old_skill_reuse(app):
    with app.app_context():
        account = seed_user()
        add_problem_progress(1, account.id, 1)
        db.session.commit()
        rebuild_user_skills(1, as_of=NOW)
        account.unlinked_at = NOW + timedelta(minutes=1)
        db.session.flush()
        db.session.add(CodeforcesAccount(
            uid=1, handle="different", linked_at=NOW + timedelta(minutes=1),
            ownership_verified=False, sync_status="PENDING"
        ))
        db.session.commit()
        with pytest.raises(SkillEstimateError):
            read_user_skills(1)
