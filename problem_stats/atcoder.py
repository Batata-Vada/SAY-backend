import time
import requests


BASE_URL = (
    "https://kenkoooo.com/atcoder/resources"
)


def fetch_json(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "SAY/1.0",
        },
    )

    response.raise_for_status()

    return response.json()


def fetch_atcoder_problems():
    problems = fetch_json(
        f"{BASE_URL}/problems.json"
    )

    #
    # Avoid hammering AtCoder Problems.
    #
    time.sleep(1)

    models = fetch_json(
        f"{BASE_URL}/problem-models.json"
    )

    output = []

    for problem in problems:
        problem_id = problem["id"]

        model = models.get(
            problem_id,
            {},
        )

        difficulty = model.get(
            "difficulty"
        )

        contest_id = problem[
            "contest_id"
        ]

        output.append({
            "platform": "ATCODER",

            "external_id":
                problem_id,

            "title":
                problem.get(
                    "name",
                    problem_id,
                ),

            "slug": None,

            "url": (
                "https://atcoder.jp/contests/"
                f"{contest_id}/tasks/"
                f"{problem_id}"
            ),

            "contest_id":
                contest_id,

            "problem_index":
                problem.get(
                    "problem_index"
                ),

            "category": None,

            "difficulty_raw": (
                {
                    "difficulty":
                        difficulty,

                    "source":
                        "atcoder-problems",
                }
                if difficulty is not None
                else None
            ),

            "tags_raw": [],

            "stats_raw": {},

            "metadata_raw": {
                "difficulty_model":
                    model or None,
            },
        })

    return output