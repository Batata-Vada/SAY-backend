"""Pure deterministic scoring for explainable Codeforces recommendations.

All scores are in [0, 1]. Ranking has no randomness or API calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import exp

MODEL_VERSION = "cf-recommend-v1"
DEFAULT_WEIGHTS = {"difficulty": 0.40, "topic": 0.35, "recency": 0.15, "diversity": 0.10}


def normalized_weights(weights):
    """Validate configuration rather than silently accepting broken weights."""
    if not isinstance(weights, dict) or set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError("RECOMMENDATION_WEIGHTS must supply difficulty, topic, recency, diversity")
    if any(type(weights[k]) not in (float, int) or not 0 <= weights[k] <= 1 for k in DEFAULT_WEIGHTS):
        raise ValueError("Recommendation weights must be numeric in [0, 1]")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one recommendation weight must be positive")
    return {k: round(weights[k] / total, 8) for k in DEFAULT_WEIGHTS}


def difficulty_fit(rating, target, window):
    if rating is None:
        return 0.35  # Separate fallback; not mixed in rated ranking.
    distance = abs(rating - target)
    return round(max(0.0, 1.0 - distance / max(window, 200)), 6)


def topic_priority(tags, mastery):
    """Prioritize weak, unknown, low-confidence tags; 0.65 = exploration prior."""
    if not tags:
        return 0.40
    scores = []
    for tag in tags:
        m = mastery.get(tag)
        if m is None or m.get("mastery_score") is None:
            scores.append(0.65)
        else:
            confidence = max(0.0, min(1.0, float(m.get("confidence") or 0)))
            score = max(0.0, min(1.0, float(m["mastery_score"])))
            scores.append((1.0 - score) * confidence + 0.65 * (1.0 - confidence))
    return round(0.7 * max(scores) + 0.3 * (sum(scores) / len(scores)), 6)


def retry_relevance(candidate_type, previous_failures, last_attempted, as_of):
    if candidate_type == "new":
        return 0.7
    if last_attempted is None:
        return 0.6
    if last_attempted.tzinfo is None:
        last_attempted = last_attempted.replace(tzinfo=timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (as_of - last_attempted).total_seconds() / 86400)
    # Avoid immediate retries, increase value after time to reflect spaced review.
    time_bonus = 0.45 * (1 - exp(-age_days / 14.0))
    failure_bonus = 0.05 * min(4, previous_failures)
    return round(min(1.0, 0.30 + time_bonus + failure_bonus), 6)


def diversity_contribution(tags, previous_tag_counts):
    if not tags:
        return 0.45
    # Prioritize tags not already represented by the current result list.
    return round(sum(1.0 / (1.0 + previous_tag_counts.get(t, 0)) for t in tags) / len(tags), 6)


def score_candidate(candidate, *, target, window, mastery, weights, previous_tag_counts, as_of):
    components = {
        "difficulty": difficulty_fit(candidate["rating"], target, window),
        "topic": topic_priority(candidate["tags"], mastery),
        "recency": retry_relevance(candidate["candidate_type"], candidate["official_failure_count"], candidate["last_attempted_at"], as_of),
        "diversity": diversity_contribution(candidate["tags"], previous_tag_counts),
    }
    score = sum(weights[k] * components[k] for k in DEFAULT_WEIGHTS)
    return round(score, 6), components


def rank_candidates(candidates, *, target, window, mastery, weights, limit, as_of=None):
    """Greedy deterministic re-ranking with coverage-aware diversity."""
    from collections import Counter
    as_of = as_of or datetime.now(timezone.utc)
    weights = normalized_weights(weights)
    remaining = list(candidates)
    tag_counts = Counter()
    ranked = []
    for _ in range(min(limit, len(remaining))):
        evaluated = [
            (score_candidate(c, target=target, window=window, mastery=mastery, weights=weights, previous_tag_counts=tag_counts, as_of=as_of), c)
            for c in remaining
        ]
        # Stable even when input order changes. Prefer new at ties, then ID.
        (score, parts), chosen = min(evaluated, key=lambda item: (
            -item[0][0], item[1]["candidate_type"] != "new", item[1]["external_id"], item[1]["problem_id"]
        ))
        ranked.append({**chosen, "score": score, "score_components": parts, "rank": len(ranked) + 1})
        tag_counts.update(chosen["tags"])
        remaining.remove(chosen)
    return ranked
