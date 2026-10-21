"""Compatibility GET endpoint for Phase 1 recommendation API.

The Step 8 POST /api/me/recommendations remains available. This GET endpoint
logs recommendations *on delivery* as requested for the experiment audit trail.
Because GET has a write side-effect, caching is explicitly disabled.
"""
from flask import Blueprint, current_app, request

from middleware.auth import login_required
from recommendations.service import RecommendationError, generate_recommendations

recommendation_api = Blueprint("recommendation_api", __name__, url_prefix="/api")


@recommendation_api.get("/recommendations")
@login_required
def recommend_for_authenticated_user(user):
    raw_limit = request.args.get("limit", "10")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return {"message": "limit must be an integer in 1..30"}, 400
    if not 1 <= limit <= 30:
        return {"message": "limit must be an integer in 1..30"}, 400
    mode = request.args.get("mode", "new")
    if mode not in {"new", "retry", "mixed"}:
        return {"message": "mode must be new, retry, or mixed"}, 400
    try:
        result = generate_recommendations(user.uid, limit=limit, mode=mode)
    except RecommendationError as exc:
        return {"message": str(exc)}, 409
    except Exception:
        current_app.logger.exception("GET recommendations failed for uid=%s", user.uid)
        return {"message": "Recommendation generation failed; check server logs"}, 500
    # Preserve Step 8 response fields and add exact Step 9 aliases.
    result["model"] = result["model_version"]
    for item in result["recommendations"]:
        item["reason"] = item["explanation"]
    return result, 200, {"Cache-Control": "private, no-store, max-age=0"}
