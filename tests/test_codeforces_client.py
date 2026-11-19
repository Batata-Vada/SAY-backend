"""Tests for the current Step 4 Codeforces client (no external HTTP requests)."""

import pytest

from codeforces.client import (
    CodeforcesClient,
    CodeforcesUnavailable,
    CodeforcesUserNotFound,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload, status_code=200):
        self.response = FakeResponse(payload, status_code)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_user_info_checks_historic_handles():
    fake = FakeSession({
        "status": "OK",
        "result": [{"handle": "tourist", "registrationTimeSeconds": 1000}],
    })
    client = CodeforcesClient(session=fake, timeout=1)
    assert client.user_info("tourist")["handle"] == "tourist"
    url, kwargs = fake.calls[0]
    assert url.endswith("/user.info")
    assert kwargs["params"] == {
        "handles": "tourist",
        "checkHistoricHandles": "true",
    }
    assert kwargs["timeout"] == 1


def test_user_status_pagination_and_rating():
    fake = FakeSession({"status": "OK", "result": []})
    client = CodeforcesClient(session=fake, timeout=1)
    assert client.user_status("tourist", from_index=11, count=50) == []
    assert fake.calls[-1][1]["params"] == {
        "handle": "tourist", "from": 11, "count": 50
    }
    assert client.user_rating("tourist") == []
    assert fake.calls[-1][0].endswith("/user.rating")
    with pytest.raises(ValueError):
        client.user_status("tourist", from_index=0)
    with pytest.raises(ValueError):
        client.user_status("tourist", count=1001)


def test_upstream_failure_returns_controlled_error():
    fake = FakeSession({"status": "FAILED", "comment": "Call limit exceeded"})
    with pytest.raises(CodeforcesUnavailable):
        CodeforcesClient(session=fake, timeout=1).user_info("tourist")


def test_nonexistent_handle():
    fake = FakeSession({
        "status": "FAILED", "comment": "User with handle tourist not found"
    })
    with pytest.raises(CodeforcesUserNotFound):
        CodeforcesClient(session=fake, timeout=1).user_info("tourist")


def test_invalid_payload():
    fake = FakeSession({"status": "OK", "result": {"handle": "tourist"}})
    with pytest.raises(CodeforcesUnavailable):
        CodeforcesClient(session=fake, timeout=1).user_info("tourist")
