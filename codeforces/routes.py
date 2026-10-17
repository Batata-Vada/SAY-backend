"""Authenticated Codeforces account linking endpoints."""

import re
from datetime import datetime, timezone

from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from codeforces.client import (
    CodeforcesClient,
    CodeforcesUnavailable,
    CodeforcesUserNotFound,
)

from database.db import db
from middleware.auth import login_required
from models.codeforces_account import CodeforcesAccount


codeforces = Blueprint(
    "codeforces",
    __name__,
    url_prefix="/api/codeforces"
)

HANDLE_RE = re.compile(r"[A-Za-z0-9_.-]{3,24}\Z")


def _active_account(uid):
    return (
        CodeforcesAccount.query
        .filter_by(uid=uid, unlinked_at=None)
        .first()
    )


@codeforces.route("/account", methods=["POST"])
@login_required
def link_account(user):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {
            "message": "Provide a JSON object"
        }, 400

    handle = data.get("handle")
    confirm_relink = data.get("confirm_relink", False)

    if (
        not isinstance(handle, str)
        or not HANDLE_RE.fullmatch(handle.strip())
    ):
        return {
            "message": "Invalid Codeforces handle format"
        }, 400

    if not isinstance(confirm_relink, bool):
        return {
            "message": "confirm_relink must be a boolean"
        }, 400

    try:
        cf_user = CodeforcesClient().user_info(
            handle.strip()
        )

    except CodeforcesUserNotFound:
        return {
            "message": "Codeforces handle does not exist"
        }, 404

    except CodeforcesUnavailable:
        return {
            "message": "Codeforces is temporarily unavailable"
        }, 503

    canonical_handle = cf_user["handle"]

    registration = cf_user.get(
        "registrationTimeSeconds"
    )

    if type(registration) is not int:
        registration = None

    try:
        active = _active_account(user.uid)

        if (
            active
            and active.handle.casefold()
            == canonical_handle.casefold()
        ):
            return {
                "message": "This Codeforces handle is already linked",
                "account": active.to_dict(),
            }, 200

        if active and not confirm_relink:
            return {
                "message": (
                    "A different Codeforces handle is already linked. "
                    "Send confirm_relink: true to replace the active link."
                )
            }, 409

        now = datetime.now(timezone.utc)

        if active:
            active.unlinked_at = now
            db.session.flush()

        record = CodeforcesAccount(
            uid=user.uid,
            handle=canonical_handle,
            ownership_verified=False,
            linked_at=now,
            unlinked_at=None,
            last_synced_at=None,
            sync_status="PENDING",
            last_sync_error=None,
            registration_time_seconds=registration,
        )

        db.session.add(record)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return {
            "message": "Conflicting account link; retry"
        }, 409

    except SQLAlchemyError:
        db.session.rollback()
        return {
            "message": "Unable to save Codeforces account"
        }, 500

    return {
        "message": (
            "Codeforces handle linked; "
            "ownership is not verified"
        ),
        "account": record.to_dict(),
    }, 201


@codeforces.route("/account", methods=["GET"])
@login_required
def get_account(user):
    record = _active_account(user.uid)

    if record is None:
        return {
            "message": "No Codeforces account linked"
        }, 404

    return {
        "account": record.to_dict()
    }, 200