"""Historical timed Codeforces evidence shared by export and model inference."""
from datetime import datetime, timezone
from statistics import fmean, pstdev

from database.db import db
from models.codeforces_submission import CodeforcesSubmission
from models.practice_session import PracticeSession
from models.problem import Problem

FEATURES = (
    "candidate_rating",
    "last_problem_rating",
    "mean_solve_time_minutes",
    "time_std_minutes",
    "timed_solved_count",
    "last_problem_solve_time_minutes",
)
FEATURE_CONTRACT = "say-practice-v1"
MIN_TRAINING_TIMED_SOLVES = 5


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def verified_solve_condition(session_as_of=None):
    requirements = (
        CodeforcesSubmission.codeforces_account_id == PracticeSession.source_account_id,
        CodeforcesSubmission.problem_id == PracticeSession.problem_id,
        CodeforcesSubmission.attribution_status == "INDIVIDUAL",
        CodeforcesSubmission.verdict == "OK",
        CodeforcesSubmission.testset == "TESTS",
        CodeforcesSubmission.submitted_at >= PracticeSession.started_at,
        CodeforcesSubmission.submitted_at <= PracticeSession.finished_at,
    )
    if session_as_of is not None:
        requirements += (
            CodeforcesSubmission.first_observed_at.is_not(None),
            CodeforcesSubmission.first_observed_at <= session_as_of,
            CodeforcesSubmission.final_verdict_observed_at.is_not(None),
            CodeforcesSubmission.final_verdict_observed_at <= session_as_of,
        )
    return db.select(CodeforcesSubmission.id).where(*requirements).exists()


def official_solved_in_session(session):
    if session.status != "FINISHED" or session.finished_at is None:
        return False
    return db.session.execute(
        db.select(CodeforcesSubmission.id).where(
            CodeforcesSubmission.codeforces_account_id == session.source_account_id,
            CodeforcesSubmission.problem_id == session.problem_id,
            CodeforcesSubmission.attribution_status == "INDIVIDUAL",
            CodeforcesSubmission.verdict == "OK",
            CodeforcesSubmission.testset == "TESTS",
            CodeforcesSubmission.submitted_at >= session.started_at,
            CodeforcesSubmission.submitted_at <= session.finished_at,
        ).limit(1)
    ).first() is not None


def collect_timed_solve_profile(uid, account, *, as_of=None, minimum=5):
    if account is None or not account.ownership_verified or account.sync_status != "SUCCEEDED":
        return None
    if type(minimum) is not int or not 1 <= minimum <= 30:
        raise ValueError("Invalid minimum timed solves")
    as_of = utc(as_of or datetime.now(timezone.utc))
    solve = verified_solve_condition(as_of)
    recent = db.session.execute(
        db.select(PracticeSession, Problem, solve.label("solved"))
        .join(Problem, PracticeSession.problem_id == Problem.id)
        .where(
            PracticeSession.uid == uid,
            PracticeSession.source_account_id == account.id,
            PracticeSession.status == "FINISHED",
            PracticeSession.finished_at.is_not(None),
            PracticeSession.finished_at < as_of,
            PracticeSession.duration_seconds.between(60, 14400),
            Problem.platform == "CODEFORCES",
        )
        .order_by(PracticeSession.finished_at.desc(), PracticeSession.id.desc())
        .limit(150)
    ).all()
    samples = []
    seen = set()
    for session, problem, solved in recent:
        if not solved or session.problem_id in seen:
            continue
        rating = problem.codeforces_rating
        if type(rating) is not int or not 800 <= rating <= 3500:
            continue
        seen.add(session.problem_id)
        samples.append((session, rating))
        if len(samples) == 30:
            break
    if len(samples) < minimum:
        return None
    durations = [s.duration_seconds / 60 for s, _ in samples]
    return {
        "last_problem_rating": samples[0][1],
        "mean_solve_time_minutes": fmean(durations),
        "time_std_minutes": pstdev(durations),
        "timed_solved_count": len(samples),
        "last_problem_solve_time_minutes": durations[0],
    }
