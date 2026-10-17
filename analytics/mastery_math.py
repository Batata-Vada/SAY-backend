"""Pure topic mastery scoring: usable without Flask/SQLAlchemy."""
from collections import defaultdict
from datetime import datetime

from analytics.difficulty import observation_weight, smoothed_success, evidence_confidence, valid_rating


def derive_topic_mastery(evidence, *, as_of: datetime) -> list[dict]:
    """Pure grouping; one distinct problem counts once toward each of its tags."""
    groups = defaultdict(list)
    for item in evidence:
        for tag in set(item.tags):
            groups[tag].append(item)

    result = []
    for tag, problems in sorted(groups.items()):
        decided = [p for p in problems if p.decided]
        rated_decided = [p for p in decided if valid_rating(p.rating)]
        support = sum(observation_weight(p, as_of) for p in decided)
        positives = sum(observation_weight(p, as_of) for p in decided if p.is_solved)
        rate = smoothed_success(positives, support) if decided else None
        conf = evidence_confidence(support, len(decided), len(problems), len(rated_decided))
        weighted_ratings = sum(p.rating * observation_weight(p, as_of) for p in rated_decided)
        denominator = sum(observation_weight(p, as_of) for p in rated_decided)
        result.append({
            "tag": tag,
            "attempted_problems": len(problems),
            "solved_problems": sum(bool(p.is_solved) for p in problems),
            "decided_problems": len(decided),
            "rated_decided_problems": len(rated_decided),
            "smoothed_success_rate": round(rate, 4) if rate is not None else None,
            "mastery_score": round(rate, 4) if rate is not None else None,
            "confidence": conf,
            "mean_rated_difficulty": round(weighted_ratings / denominator, 1) if denominator else None,
        })
    return result


