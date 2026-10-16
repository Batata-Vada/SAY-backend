"""Smoke tests against a running SAY backend."""

import os
import requests


BASE_URL = os.getenv(
    "SAY_BASE_URL",
    "http://127.0.0.1:5001"
).rstrip("/")


def main():
    username = os.getenv("SAY_TEST_USERNAME")
    password = os.getenv("SAY_TEST_PASSWORD")

    if not username or not password:
        raise SystemExit(
            "Set SAY_TEST_USERNAME and SAY_TEST_PASSWORD"
        )

    response = requests.post(
        f"{BASE_URL}/login",
        json={
            "name": username,
            "password": password
        },
        timeout=15
    )

    response.raise_for_status()

    token = response.json()["token"]

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("PASS: login")

    response = requests.get(
        f"{BASE_URL}/me",
        headers=headers,
        timeout=15
    )

    response.raise_for_status()

    profile = response.json()

    assert profile["name"] == username
    assert "password" not in profile

    print("PASS: authenticated /me")

    response = requests.get(
        f"{BASE_URL}/users",
        timeout=15
    )

    assert response.status_code == 401

    print("PASS: unauthenticated user listing blocked")

    response = requests.get(
        f"{BASE_URL}/users/{profile['uid']}",
        headers=headers,
        timeout=15
    )

    assert response.status_code == 200

    print("PASS: own profile accessible")

    if profile["privilege"] != "admin":
        response = requests.get(
            f"{BASE_URL}/users",
            headers=headers,
            timeout=15
        )

        assert response.status_code == 403

        print("PASS: non-admin user listing blocked")

    response = requests.post(
        f"{BASE_URL}/logout",
        headers=headers,
        timeout=15
    )

    response.raise_for_status()

    response = requests.get(
        f"{BASE_URL}/me",
        headers=headers,
        timeout=15
    )

    assert response.status_code == 401

    print("PASS: logout revoked session")
    print("All smoke tests passed")


if __name__ == "__main__":
    main()