"""Reusable client for the official Codeforces API."""

import requests

from flask import current_app


class CodeforcesError(Exception):
    pass


class CodeforcesUserNotFound(CodeforcesError):
    pass


class CodeforcesUnavailable(CodeforcesError):
    pass


class CodeforcesClient:
    BASE_URL = "https://codeforces.com/api"

    def __init__(self, session=None, timeout=None):
        self.session = session or requests.Session()

        self.timeout = (
            timeout
            if timeout is not None
            else current_app.config.get(
                "CODEFORCES_TIMEOUT_SECONDS", 30
            )
        )

    def _get(self, method, params):
        try:
            response = self.session.get(
                f"{self.BASE_URL}/{method}",
                params=params,
                timeout=self.timeout,
                headers={
                    "User-Agent": "SAY/1.0 (Codeforces integration)"
                },
            )
        except requests.RequestException as exc:
            raise CodeforcesUnavailable(
                "Codeforces is temporarily unavailable"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CodeforcesUnavailable(
                "Codeforces returned an invalid response"
            ) from exc

        if (
            isinstance(payload, dict)
            and payload.get("status") == "FAILED"
        ):
            comment = str(
                payload.get("comment", "")
            ).lower()

            if method == "user.info" and any(
                phrase in comment
                for phrase in (
                    "not found",
                    "does not exist",
                    "no such user",
                )
            ):
                raise CodeforcesUserNotFound(
                    "Codeforces handle not found"
                )

            raise CodeforcesUnavailable(
                "Codeforces could not complete the request"
            )

        if response.status_code >= 400:
            raise CodeforcesUnavailable(
                "Codeforces returned an HTTP error"
            )

        if (
            not isinstance(payload, dict)
            or payload.get("status") != "OK"
        ):
            raise CodeforcesUnavailable(
                "Unexpected Codeforces response"
            )

        return payload.get("result")

    def user_info(self, handle):
        users = self._get(
            "user.info",
            {
                "handles": handle,
                "checkHistoricHandles": "true",
            }
        )

        if not isinstance(users, list) or len(users) != 1:
            raise CodeforcesUnavailable(
                "Invalid Codeforces user.info result"
            )

        user = users[0]

        if (
            not isinstance(user, dict)
            or not isinstance(user.get("handle"), str)
        ):
            raise CodeforcesUnavailable(
                "Invalid Codeforces user data"
            )

        return user

    def user_status(self, handle, from_index=1, count=100):
        if (
            type(from_index) is not int
            or from_index < 1
            or type(count) is not int
            or not 1 <= count <= 1000
        ):
            raise ValueError(
                "Invalid submission pagination"
            )

        result = self._get(
            "user.status",
            {
                "handle": handle,
                "from": from_index,
                "count": count,
            }
        )

        if not isinstance(result, list):
            raise CodeforcesUnavailable(
                "Invalid Codeforces submissions"
            )

        return result

    def user_rating(self, handle):
        result = self._get(
            "user.rating",
            {"handle": handle}
        )

        if not isinstance(result, list):
            raise CodeforcesUnavailable(
                "Invalid Codeforces rating history"
            )

        return result