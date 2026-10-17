"""Pure and deterministic aggregation of official Codeforces submissions.

Inputs must already be scoped to an active account, an actual CODEFORCES
catalog problem, and INDIVIDUAL author attribution.
"""

from dataclasses import dataclass
from datetime import timezone

# Explicitly terminal verdicts. Unknown/novel verdicts are NOT counted as failures.
FAILURE_VERDICTS = frozenset({
    "FAILED", "PARTIAL", "COMPILATION_ERROR", "RUNTIME_ERROR",
    "WRONG_ANSWER", "PRESENTATION_ERROR", "TIME_LIMIT_EXCEEDED",
    "MEMORY_LIMIT_EXCEEDED", "IDLENESS_LIMIT_EXCEEDED",
    "SECURITY_VIOLATED", "CRASHED", "INPUT_PREPARATION_CRASHED",
    "CHALLENGED", "REJECTED",
})


def as_utc(value):
    """SQLite loads naive UTC timestamps; normalize for stable comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify_official_submission(verdict, testset):
    """Return one of FINAL_OK, PROVISIONAL_OK, FAILURE, PENDING, OTHER."""
    if verdict == "OK":
        return "FINAL_OK" if testset == "TESTS" else "PROVISIONAL_OK"
    if verdict is None or verdict == "TESTING":
        return "PENDING"
    if verdict in FAILURE_VERDICTS:
        # An explicit non-OK official verdict is a failed attempt, including
        # pretest failures. Unlike PRETESTS OK, these are not accepted solves.
        return "FAILURE"
    # E.g. SKIPPED or an enum unknown to this version of SAY.
    return "OTHER"


@dataclass
class ProgressEvidence:
    problem_id: int
    official_submission_count: int = 0
    official_failure_count: int = 0
    official_final_ok_count: int = 0
    official_pending_count: int = 0
    official_provisional_ok_count: int = 0
    official_unclassified_count: int = 0
    first_attempted_at: object = None
    first_solved_at: object = None
    last_submitted_at: object = None
    progress_updated_at: object = None

    @property
    def is_solved(self):
        return self.official_final_ok_count > 0

    def incorporate(self, submission):
        submitted = as_utc(submission.submitted_at)
        checked = as_utc(submission.last_checked_at)
        if submitted is None or checked is None:
            raise ValueError("Official submission is missing required timestamps")

        self.official_submission_count += 1
        self.first_attempted_at = min(self.first_attempted_at, submitted) if self.first_attempted_at else submitted
        self.last_submitted_at = max(self.last_submitted_at, submitted) if self.last_submitted_at else submitted
        self.progress_updated_at = max(self.progress_updated_at, checked) if self.progress_updated_at else checked

        category = classify_official_submission(submission.verdict, submission.testset)
        if category == "FINAL_OK":
            self.official_final_ok_count += 1
            self.first_solved_at = min(self.first_solved_at, submitted) if self.first_solved_at else submitted
        elif category == "PROVISIONAL_OK":
            self.official_provisional_ok_count += 1
        elif category == "FAILURE":
            self.official_failure_count += 1
        elif category == "PENDING":
            self.official_pending_count += 1
        else:
            self.official_unclassified_count += 1


def aggregate_submissions(submissions):
    """Return problem_id -> ProgressEvidence (same output regardless row order)."""
    result = {}
    for submission in submissions:
        if submission.attribution_status != "INDIVIDUAL":
            continue
        if submission.problem_id is None:
            continue
        item = result.setdefault(submission.problem_id, ProgressEvidence(submission.problem_id))
        item.incorporate(submission)
    return result
