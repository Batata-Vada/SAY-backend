import requests


URL = "https://codeforces.com/api/problemset.problems"


def fetch_codeforces_problems():
    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "SAY/1.0",
        },
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "OK":
        raise RuntimeError(
            "Codeforces API returned failure"
        )

    result = payload["result"]

    problems = result["problems"]
    statistics = result["problemStatistics"]

    stats_by_id = {}

    for stat in statistics:
        contest_id = stat.get("contestId")
        index = stat["index"]

        key = (contest_id, index)

        stats_by_id[key] = stat

    output = []

    for problem in problems:
        if problem.get("type") != "PROGRAMMING":
            continue

        contest_id = problem.get("contestId")
        index = problem["index"]

        stats = stats_by_id.get(
            (contest_id, index),
            {},
        )

        if contest_id is not None:
            external_id = f"{contest_id}:{index}"

            url = (
                "https://codeforces.com/problemset/problem/"
                f"{contest_id}/{index}"
            )
        else:
            problemset_name = problem.get(
                "problemsetName",
                "unknown",
            )

            external_id = (
                f"{problemset_name}:{index}"
            )

            url = "https://codeforces.com/problemset"

        rating = problem.get("rating")

        output.append({
            "platform": "CODEFORCES",

            "external_id": external_id,

            "title": problem["name"],

            "url": url,

            "contest_id": (
                str(contest_id)
                if contest_id is not None
                else None
            ),

            "problem_index": index,

            "category": None,

            "difficulty_raw": (
                {
                    "rating": rating,
                }
                if rating is not None
                else None
            ),

            "tags_raw": problem.get(
                "tags",
                [],
            ),

            "stats_raw": {
                "solved_count":
                    stats.get("solvedCount"),
            },

            "metadata_raw": {
                "points":
                    problem.get("points"),

                "problemset_name":
                    problem.get("problemsetName"),
            },
        })

    return output