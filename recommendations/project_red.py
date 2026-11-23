"""Validate and serve a real-outcome Project Red probability model."""
import json
import math
from functools import lru_cache
from pathlib import Path

from flask import current_app

from recommendations.feature_history import (
    FEATURE_CONTRACT, FEATURES, collect_timed_solve_profile,
    official_solved_in_session,
)


def collect_features(uid, account, progress_rows, minimum=5):
    return collect_timed_solve_profile(uid, account, minimum=minimum)


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


@lru_cache(maxsize=4)
def _load_artifact(path):
    with Path(path).open(encoding="utf-8") as source:
        artifact = json.load(source)
    if not isinstance(artifact, dict):
        raise ValueError("Invalid Project Red artifact")
    if artifact.get("artifact_schema_version") != 1:
        raise ValueError("Unsupported Project Red artifact schema")
    if artifact.get("model_type") != "logistic-regression":
        raise ValueError("Unsupported Project Red model type")
    if artifact.get("feature_contract") != FEATURE_CONTRACT:
        raise ValueError("Project Red feature contract mismatch")
    if tuple(artifact.get("features", ())) != FEATURES:
        raise ValueError("Project Red feature order mismatch")
    version = artifact.get("model_version")
    if not isinstance(version, str) or not 1 <= len(version) <= 32:
        raise ValueError("Invalid model version")
    for key in ("x_mean", "x_scale", "coef"):
        values = artifact.get(key)
        if not isinstance(values, list) or len(values) != len(FEATURES):
            raise ValueError(f"Invalid artifact {key}")
        if not all(_finite(v) for v in values):
            raise ValueError(f"Non-finite artifact {key}")
    if not _finite(artifact.get("intercept")):
        raise ValueError("Invalid model intercept")
    if any(scale <= 0 for scale in artifact["x_scale"]):
        raise ValueError("Invalid model scaler")
    if artifact["coef"][0] >= 0:
        raise ValueError("Model probability must decrease with candidate difficulty")
    target = artifact.get("target_probability", 0.60)
    bounds = artifact.get("acceptable_probability_range", [0.45, 0.75])
    grid = artifact.get("rating_grid", [800, 3500, 100])
    if not _finite(target) or not 0 < target < 1:
        raise ValueError("Invalid target success probability")
    if (not isinstance(bounds, list) or len(bounds) != 2 or
        not all(_finite(x) for x in bounds) or
        not 0 < bounds[0] < target < bounds[1] < 1):
        raise ValueError("Invalid probability policy bounds")
    if (not isinstance(grid, list) or len(grid) != 3 or
        not all(type(x) is int for x in grid) or
        not 800 <= grid[0] < grid[1] <= 3500 or
        grid[2] <= 0 or grid[2] % 100 != 0):
        raise ValueError("Invalid rating grid")
    return artifact


def _artifact():
    path = Path(current_app.config["PROJECT_RED_MODEL_PATH"])
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return _load_artifact(str(path.resolve()))


def solve_probability(profile, candidate_rating, artifact):
    values = {**profile, "candidate_rating": candidate_rating}
    z = artifact["intercept"]
    for name, mean, scale, coefficient in zip(
        artifact["features"], artifact["x_mean"], artifact["x_scale"], artifact["coef"]
    ):
        value = values[name]
        if not _finite(value):
            raise ValueError("Invalid prediction feature")
        z += coefficient * ((value - mean) / scale)
    if not math.isfinite(z):
        raise ValueError("Non-finite model prediction")
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def predict(features):
    artifact = _artifact()
    start, stop, step = artifact.get("rating_grid", [800, 3500, 100])
    target = artifact.get("target_probability", 0.60)
    low, high = artifact.get("acceptable_probability_range", [0.45, 0.75])
    options = [
        (rating, solve_probability(features, rating, artifact))
        for rating in range(start, stop + 1, step)
    ]
    suitable = [(rating, prob) for rating, prob in options if low <= prob <= high]
    if not suitable:
        raise ValueError("No calibrated difficulty window for the user")
    center = min(suitable, key=lambda item: (abs(item[1] - target), item[0]))[0]
    lower = max(start, min(rating for rating, _ in suitable))
    upper = min(stop, max(rating for rating, _ in suitable))
    if lower == upper:
        lower = max(start, lower - step)
        upper = min(stop, upper + step)
    if lower >= upper:
        raise ValueError("Empty Project Red difficulty window")
    return {
        "center": center,
        "width": upper - lower,
        "lower_bound": lower,
        "upper_bound": upper,
        "model_version": artifact["model_version"],
    }
