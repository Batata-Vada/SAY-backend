"""Pure and explainable Codeforces practice readiness estimation (Step 7).

No SQLAlchemy dependency: suitable for deterministic unit tests and iteration.
One ProblemEvidence = one distinct canonical problem, not one submission.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp

MODEL_VERSION = "cf-skills-v1"
ALPHA = 1.5
BETA = 1.5
BAND_WIDTH = 200
MIN_DECIDED_IN_BAND = 3
MIN_SUPPORT_IN_BAND = 2.0
SUCCESS_THRESHOLD = 0.60


@dataclass(frozen=True)
class ProblemEvidence:
    problem_id: int
    tags: tuple[str, ...]
    rating: int | None
    is_solved: bool
    official_failure_count: int
    last_submitted_at: datetime

    @property
    def decided(self) -> bool:
        # A final solve or any explicit official failure gives usable outcome
        # evidence. Pending/provisional-only attempts remain unknown.
        return self.is_solved or self.official_failure_count > 0


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:  # SQLite often loads UTC timestamps as naive.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def recency_weight(value: datetime, as_of: datetime) -> float:
    """Decays to a 0.25 floor; half-life about 180 days above the floor."""
    age_days = max(0.0, (_utc(as_of) - _utc(value)).total_seconds() / 86400.0)
    return 0.25 + 0.75 * exp(-age_days / 260.0)


def valid_rating(value) -> bool:
    return type(value) is int and 0 < value <= 5000


def difficulty_weight(rating: int | None) -> float:
    """Harder rated problems are stronger evidence at equal outcomes."""
    if not valid_rating(rating):
        return 0.65  # Unrated observations carry less statistical weight.
    position = min(1.0, max(0.0, (rating - 800) / 1600.0))
    return 0.75 + 0.90 * position


def observation_weight(evidence: ProblemEvidence, as_of: datetime) -> float:
    return recency_weight(evidence.last_submitted_at, as_of) * difficulty_weight(evidence.rating)


def smoothed_success(positives: float, support: float) -> float:
    return (positives + ALPHA) / (support + ALPHA + BETA)


def evidence_confidence(support: float, decided: int, attempted: int, rated: int) -> float:
    if not decided or not attempted:
        return 0.0
    quantity = min(1.0, support / 8.0)
    completeness = decided / attempted
    rating_quality = 0.65 + 0.35 * (rated / decided)
    return round(quantity * completeness * rating_quality, 4)


def estimate_difficulty_readiness(evidence, *, as_of: datetime) -> dict:
    """Estimate a *problem-rating band*, not official contest rating.

    A band needs at least three decided problems, >=2 effective observations,
    and >=60% smoothed solved probability. The highest qualifying band wins.
    Unknown-only and unrated data never fake a difficulty estimate.
    """
    evidence = list(evidence)
    rated = [p for p in evidence if valid_rating(p.rating)]
    bands = defaultdict(list)
    for item in rated:
        bands[(item.rating // BAND_WIDTH) * BAND_WIDTH].append(item)

    results = []
    qualifying = []
    for band_start, problems in sorted(bands.items()):
        decided = [p for p in problems if p.decided]
        support = sum(recency_weight(p.last_submitted_at, as_of) for p in decided)
        successes = sum(recency_weight(p.last_submitted_at, as_of) for p in decided if p.is_solved)
        rate = smoothed_success(successes, support) if decided else None
        confidence = evidence_confidence(support, len(decided), len(problems), len(decided))
        band = {
            "band_start": band_start,
            "band_end_exclusive": band_start + BAND_WIDTH,
            "attempted_problems": len(problems),
            "decided_problems": len(decided),
            "solved_problems": sum(p.is_solved for p in problems),
            "smoothed_success_rate": round(rate, 4) if rate is not None else None,
            "effective_evidence": round(support, 3),
            "confidence": confidence,
        }
        results.append(band)
        if (len(decided) >= MIN_DECIDED_IN_BAND
                and support >= MIN_SUPPORT_IN_BAND
                and rate is not None and rate >= SUCCESS_THRESHOLD):
            qualifying.append(band)

    best = max(qualifying, key=lambda b: b["band_start"]) if qualifying else None
    return {
        "readiness_rating": best["band_start"] if best else None,
        "confidence": best["confidence"] if best else 0.0,
        "rated_attempted_problems": len(rated),
        "rated_decided_problems": sum(p.decided for p in rated),
        "rated_solved_problems": sum(p.is_solved for p in rated),
        "rating_bands": results,
    }
