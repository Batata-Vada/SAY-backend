"""Integration tests: `python -m pytest tests/test_codeforces_linking.py -v`.

These tests use isolated in-memory SQLite and mocked Codeforces, not your real DB.
"""

from unittest.mock import patch

import pytest

from database.db import db
from main import create_app
from middleware.auth import issue_session_token, token_digest
from models.codeforces_account import CodeforcesAccount
from models.session import Session
from models.users import User


@pytest.fixture()
def api():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "only-for-unit-tests-not-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "CORS_ORIGINS": ["http://localhost:5173"],
    })
    with app.app_context():
        db.create_all()  # Safe in an isolated test DB, not in production main.py.
        user = User(name="test_linker", email="test@example.com",
                    password="not-a-real-password", privilege="user")
        db.session.add(user)
        db.session.commit()
        token = issue_session_token(user.uid)
        db.session.add(Session(uid=user.uid, token=token_digest(token)))
        db.session.commit()
        yield app.test_client(), {"Authorization": f"Bearer {token}"}
        db.session.remove()
        db.drop_all()


def test_requires_authentication(api):
    client, _ = api
    r = client.get("/api/codeforces/account")
    assert r.status_code == 401


def test_link_and_retrieve(api):
    client, auth = api
    with patch("codeforces.routes.CodeforcesClient.user_info", return_value={
        "handle": "tourist", "registrationTimeSeconds": 1000,
    }):
        r = client.post("/api/codeforces/account", json={"handle": "TOURIST"}, headers=auth)
        assert r.status_code == 201
        assert r.json["account"]["ownership_verified"] is False
        assert r.json["account"]["handle"] == "tourist"
        again = client.post("/api/codeforces/account", json={"handle": "tourist"}, headers=auth)
        assert again.status_code == 200

    read = client.get("/api/codeforces/account", headers=auth)
    assert read.status_code == 200
    assert read.json["account"]["handle"] == "tourist"
    assert db.session.query(CodeforcesAccount).count() == 1


def test_explicit_relink_archives_previous(api):
    client, auth = api
    with patch("codeforces.routes.CodeforcesClient.user_info", side_effect=[
        {"handle": "tourist"}, {"handle": "Petr"}, {"handle": "Petr"}
    ]):
        assert client.post("/api/codeforces/account", json={"handle": "tourist"}, headers=auth).status_code == 201
        assert client.post("/api/codeforces/account", json={"handle": "Petr"}, headers=auth).status_code == 409
        assert client.post("/api/codeforces/account", json={
            "handle": "Petr", "confirm_relink": True,
        }, headers=auth).status_code == 201

    rows = db.session.query(CodeforcesAccount).order_by(CodeforcesAccount.id).all()
    assert len(rows) == 2
    assert rows[0].unlinked_at is not None
    assert rows[1].unlinked_at is None


def test_invalid_handle_format(api):
    client, auth = api
    resp = client.post("/api/codeforces/account", json={"handle": "???"}, headers=auth)
    assert resp.status_code == 400
