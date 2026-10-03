from datetime import datetime, timezone

from database.db import db
from models.problem import Problem

from problem_stats.codeforces import (
    fetch_codeforces_problems,
)

from problem_stats.leetcode import (
    fetch_leetcode_problems,
)

from problem_stats.atcoder import (
    fetch_atcoder_problems,
)

from problem_stats.cses import (
    fetch_cses_problems,
)


COLLECTORS = {
    "CODEFORCES":
        fetch_codeforces_problems,

    "LEETCODE":
        fetch_leetcode_problems,

    "ATCODER":
        fetch_atcoder_problems,

    "CSES":
        fetch_cses_problems,
}


def upsert_problem(data):
    now = datetime.now(
        timezone.utc
    )

    problem = Problem.query.filter_by(
        platform=data["platform"],
        external_id=data["external_id"],
    ).first()

    if problem is None:
        problem = Problem(
            platform=
                data["platform"],

            external_id=
                data["external_id"],

            first_seen_at=now,
        )

        db.session.add(problem)

    problem.title = data["title"]

    problem.slug = data.get(
        "slug"
    )

    problem.url = data["url"]

    problem.contest_id = data.get(
        "contest_id"
    )

    problem.problem_index = data.get(
        "problem_index"
    )

    problem.category = data.get(
        "category"
    )

    problem.difficulty_raw = data.get(
        "difficulty_raw"
    )

    problem.tags_raw = data.get(
        "tags_raw",
        [],
    )

    problem.stats_raw = data.get(
        "stats_raw",
        {},
    )

    problem.metadata_raw = data.get(
        "metadata_raw",
        {},
    )

    problem.last_seen_at = now
    problem.last_fetched_at = now

    return problem


def sync_platform(platform):
    collector = COLLECTORS[
        platform
    ]

    print(
        f"[sync] Fetching {platform}..."
    )

    problems = collector()

    print(
        f"[sync] Received "
        f"{len(problems)} problems"
    )

    for index, data in enumerate(
        problems,
        start=1,
    ):
        upsert_problem(data)

        #
        # Avoid keeping thousands
        # of dirty ORM objects around.
        #
        if index % 500 == 0:
            db.session.commit()

            print(
                f"[sync] {platform}: "
                f"{index}/{len(problems)}"
            )

    db.session.commit()

    print(
        f"[sync] Finished {platform}"
    )

    return len(problems)


def sync_all():
    results = {}

    for platform in COLLECTORS:
        try:
            results[platform] = (
                sync_platform(platform)
            )

        except Exception as exc:
            #
            # LeetCode breaking should
            # not stop Codeforces, etc.
            #
            db.session.rollback()

            print(
                f"[sync] {platform} failed:"
                f" {exc}"
            )

            results[platform] = {
                "error": str(exc),
            }

    return results