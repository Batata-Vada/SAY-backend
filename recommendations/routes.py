"""Authenticated recommendation generation and personal audit history."""
from flask import Blueprint, current_app, request
from middleware.auth import login_required
from recommendations.service import (
    RecommendationError, generate_recommendations, read_recommendation_history,
)

recommendations = Blueprint("recommendations", __name__, url_prefix="/api/me/recommendations")


@recommendations.post("")
@login_required
def generate_for_me(user):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"message": "Expected a JSON object"}, 400
    limit = data.get("limit", 10)
    mode = data.get("mode", "new")
    if type(limit) is not int or not 1 <= limit <= 30:
        return {"message": "limit must be an integer in 1..30"}, 400
    if not isinstance(mode, str) or mode not in ("new", "retry", "mixed"):
        return {"message": "mode must be new, retry, or mixed"}, 400
    try:
        return generate_recommendations(user.uid, limit=limit, mode=mode), 200
    except RecommendationError as exc:
        return {"message": str(exc)}, 409
    except Exception:
        current_app.logger.exception("Recommendation generation failed for uid=%s", user.uid)
        return {"message": "Recommendation generation failed; check server logs"}, 500


@recommendations.get("/history")
@login_required
def history_for_me(user):
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
        return read_recommendation_history(user.uid, limit=limit, offset=offset), 200
    except (TypeError, ValueError):
        return {"message": "limit must be 1..100 and offset >= 0"}, 400
