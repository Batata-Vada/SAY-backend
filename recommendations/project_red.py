import json
import logging
from functools import lru_cache
from pathlib import Path
from statistics import fmean, pstdev

from sqlalchemy import func

from database.db import db
from models.codeforces_submission import CodeforcesSubmission
from models.practice_session import PracticeSession
from models.problem import Problem
from models.user_problem_progress import UserProblemProgress

logger = logging.getLogger(__name__)
ARTIFACTS = Path(__file__).resolve().parent / "artifacts" / "project_red_v5"
FEATURES = (
    "user_rating", "last_problem_rating", "mean_solve_time_minutes",
    "time_std_minutes", "problems_solved", "last_problem_solve_time_minutes",
)


def official_solved_in_session(session):
    if session.status != "FINISHED" or session.finished_at is None:
        return False
    return db.session.execute(db.select(CodeforcesSubmission.id).where(
        CodeforcesSubmission.codeforces_account_id == session.source_account_id,
        CodeforcesSubmission.problem_id == session.problem_id,
        CodeforcesSubmission.attribution_status == "INDIVIDUAL",
        CodeforcesSubmission.verdict == "OK",
        CodeforcesSubmission.testset == "TESTS",
        CodeforcesSubmission.submitted_at >= session.started_at,
        CodeforcesSubmission.submitted_at <= session.finished_at,
    ).limit(1)).first() is not None


def solved_problem_count(uid, account_id):
    return db.session.execute(db.select(func.count()).select_from(UserProblemProgress).where(
        UserProblemProgress.uid == uid,
        UserProblemProgress.source_account_id == account_id,
        UserProblemProgress.is_solved.is_(True),
    )).scalar_one()


def collect_features(uid, account, progress_rows, minimum=5):
    if account is None or not account.ownership_verified or account.sync_status != "SUCCEEDED":
        return None
    if account.current_rating is None or account.rated_contests is None:
        return None
    if not 0 <= account.current_rating <= 5000:
        return None

    sessions = db.session.execute(db.select(PracticeSession, Problem).join(
        Problem, PracticeSession.problem_id == Problem.id
    ).where(
        PracticeSession.uid == uid,
        PracticeSession.source_account_id == account.id,
        PracticeSession.status == "FINISHED",
        PracticeSession.duration_seconds.between(60, 14400),
        Problem.platform == "CODEFORCES",
    ).order_by(PracticeSession.finished_at.desc(), PracticeSession.id.desc()).limit(150)).all()

    samples = []
    seen = set()
    for session, problem in sessions:
        if session.problem_id in seen or not official_solved_in_session(session):
            continue
        seen.add(session.problem_id)
        if type(problem.codeforces_rating) is not int:
            continue
        if not 800 <= problem.codeforces_rating <= 3500:
            continue
        samples.append((session, problem))
        if len(samples) == 30:
            break
    if len(samples) < minimum:
        return None

    durations = [session.duration_seconds / 60 for session, _ in samples]
    latest, latest_problem = samples[0]
    return {
        "user_rating": account.current_rating,
        "last_problem_rating": latest_problem.codeforces_rating,
        "mean_solve_time_minutes": fmean(durations),
        "time_std_minutes": pstdev(durations),
        "problems_solved": sum(bool(p.is_solved) for p in progress_rows),
        "last_problem_solve_time_minutes": latest.duration_seconds / 60,
    }


@lru_cache(maxsize=1)
def _runtime():
    import numpy as np
    import onnxruntime as ort

    with (ARTIFACTS / "scalers.json").open(encoding="utf-8") as stream:
        config = json.load(stream)
    if tuple(config["features"]) != FEATURES:
        raise ValueError("Model feature order does not match its scalers")
    session = ort.InferenceSession(str(ARTIFACTS / "gama_v5.onnx"),
                                   providers=["CPUExecutionProvider"])
    if len(session.get_inputs()) != 1:
        raise ValueError("Unexpected model input count")
    return session, config, np


def predict(features):
    session, config, np = _runtime()
    vector = np.array([[features[name] for name in FEATURES]], dtype=np.float32)
    if not np.isfinite(vector).all():
        raise ValueError("Invalid model features")
    x_scale = np.asarray(config["x_scale"], dtype=np.float32)
    x_mean = np.asarray(config["x_mean"], dtype=np.float32)
    if not np.all(x_scale > 0):
        raise ValueError("Invalid input scaler")
    normalized = (vector - x_mean) / x_scale
    output = np.asarray(session.run(None, {
        session.get_inputs()[0].name: normalized
    })[0], dtype=np.float64).reshape(-1)
    if output.shape != (2,) or not np.isfinite(output).all():
        raise ValueError("Unexpected model output")
    prediction = output * np.asarray(config["y_scale"]) + np.asarray(config["y_mean"])
    center, width = map(float, prediction)
    if width <= 0:
        raise ValueError("Predicted width must be positive")
    center = max(800, min(3500, center))
    width = max(120, min(1200, width))
    lower = max(800, center - width / 2)
    upper = min(3500, center + width / 2)
    if lower >= upper:
        raise ValueError("Predicted range is empty")
    return {"center": round(center), "width": round(width),
            "lower_bound": round(lower), "upper_bound": round(upper)}
