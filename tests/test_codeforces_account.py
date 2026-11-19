"""Integration tests for Step 4 routes with an isolated in-memory SQLite DB."""

from unittest.mock import patch

import pytest
from flask import Flask

from codeforces.client import CodeforcesUnavailable, CodeforcesUserNotFound
from codeforces.routes import codeforces
from database.db import db
from middleware.auth import issue_session_token, token_digest
from models.codeforces_account import CodeforcesAccount
from models.session import Session
from models.users import User


@pytest.fixture()
def api():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-only-not-a-real-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_MAX_AGE_SECONDS=3600,
        CODEFORCES_TIMEOUT_SECONDS=2,
    )
    db.init_app(app)
    app.register_blueprint(codeforces)

    with app.app_context():
        db.create_all()  # Only for disposable, isolated test DB.
        user = User(
            name="tester", email="tester@example.test",
            password="dummy", privilege="user"
        )
        db.session.add(user)
        db.session.commit()
        token = issue_session_token(user.uid)
        db.session.add(Session(uid=user.uid, token=token_digest(token)))
        db.session.commit()
        yield app.test_client(), {"Authorization": f"Bearer {token}"}
        db.session.remove()
        db.drop_all()


def test_authentication_is_required(api):
    client, _ = api
    assert client.get("/api/codeforces/account").status_code == 401
    assert client.post(
        "/api/codeforces/account", json={"handle": "tourist"}
    ).status_code == 401


def test_link_get_and_idempotency(api):
    client, headers = api
    with patch("codeforces.routes.CodeforcesClient.user_info", return_value={
        "handle": "tourist", "registrationTimeSeconds": 1000
    }):
        response = client.post(
            "/api/codeforces/account", json={"handle": "tourist"}, headers=headers
        )
        assert response.status_code == 201
        assert response.json["account"]["ownership_verified"] is False
        assert response.json["account"]["sync_status"] == "PENDING"
        assert client.post(
            "/api/codeforces/account", json={"handle": "tourist"}, headers=headers
        ).status_code == 200

    retrieved = client.get("/api/codeforces/account", headers=headers)
    assert retrieved.status_code == 200
    assert retrieved.json["account"]["handle"] == "tourist"
    assert db.session.query(CodeforcesAccount).count() == 1


def test_relink_archives_previous_account(api):
    client, headers = api
    with patch("codeforces.routes.CodeforcesClient.user_info", side_effect=[
        {"handle": "tourist"}, {"handle": "Petr"}, {"handle": "Petr"}
    ]):
        assert client.post(
            "/api/codeforces/account", json={"handle": "tourist"}, headers=headers
        ).status_code == 201
        assert client.post(
            "/api/codeforces/account", json={"handle": "Petr"}, headers=headers
        ).status_code == 409
        assert client.post(
            "/api/codeforces/account",
            json={"handle": "Petr", "confirm_relink": True},
            headers=headers,
        ).status_code == 201

    rows = db.session.query(CodeforcesAccount).order_by(CodeforcesAccount.id).all()
    assert len(rows) == 2
    assert rows[0].unlinked_at is not None
    assert rows[1].unlinked_at is None
    assert rows[0].handle == "tourist"
    assert rows[1].handle == "Petr"


def test_validation_and_not_found(api):
    client, headers = api
    assert client.post(
        "/api/codeforces/account", json={"handle": "a;b"}, headers=headers
    ).status_code == 400
    assert client.post(
        "/api/codeforces/account", json={"handle": 123}, headers=headers
    ).status_code == 400
    assert client.post(
        "/api/codeforces/account",
        json={"handle": "tourist", "confirm_relink": "yes"}, headers=headers
    ).status_code == 400
    with patch(
        "codeforces.routes.CodeforcesClient.user_info",
        side_effect=CodeforcesUserNotFound("not found"),
    ):
        assert client.post(
            "/api/codeforces/account", json={"handle": "notfound123"}, headers=headers
        ).status_code == 404
    with patch(
        "codeforces.routes.CodeforcesClient.user_info",
        side_effect=CodeforcesUnavailable("offline"),
    ):
        assert client.post(
            "/api/codeforces/account", json={"handle": "unavailable"}, headers=headers
        ).status_code == 503


def test_missing_link(api):
    client, headers = api
    assert client.get("/api/codeforces/account", headers=headers).status_code == 404


def test_other_user_cannot_read_link(api):
    client, headers = api
    with patch("codeforces.routes.CodeforcesClient.user_info", return_value={
        "handle": "tourist"
    }):
        assert client.post(
            "/api/codeforces/account", json={"handle": "tourist"}, headers=headers
        ).status_code == 201

    second = User(
        name="second", email="second@example.test", password="dummy", privilege="user"
    )
    db.session.add(second)
    db.session.commit()
    token = issue_session_token(second.uid)
    db.session.add(Session(uid=second.uid, token=token_digest(token)))
    db.session.commit()
    assert client.get(
        "/api/codeforces/account", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 404
