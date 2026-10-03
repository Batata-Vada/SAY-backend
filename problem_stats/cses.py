import re

import requests
from bs4 import BeautifulSoup


URL = "https://cses.fi/problemset/"


def fetch_cses_problems():
    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "SAY/1.0",
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    output = []

    current_category = None

    #
    # Traverse headings + problem links
    # in document order.
    #
    for element in soup.find_all(
        ["h2", "a"]
    ):
        if element.name == "h2":
            current_category = (
                element
                .get_text(strip=True)
            )

            continue

        href = element.get("href", "")

        if not href.startswith(
            "/problemset/task/"
        ):
            continue

        match = re.search(
            r"/problemset/task/(\d+)",
            href,
        )

        if not match:
            continue

        external_id = match.group(1)

        title = element.get_text(
            strip=True
        )

        parent_text = (
            element.parent
            .get_text(
                " ",
                strip=True,
            )
        )

        #
        # CSES displays counters like:
        #
        # solved / attempted
        #
        stat_match = re.search(
            r"(\d+)\s*/\s*(\d+)",
            parent_text,
        )

        solved = None
        attempted = None

        if stat_match:
            solved = int(
                stat_match.group(1)
            )

            attempted = int(
                stat_match.group(2)
            )

        acceptance_ratio = None

        if (
            solved is not None
            and attempted
        ):
            acceptance_ratio = (
                solved / attempted
            )

        output.append({
            "platform": "CSES",

            "external_id":
                external_id,

            "title":
                title,

            "slug": None,

            "url": (
                "https://cses.fi"
                f"{href}"
            ),

            "contest_id": None,

            "problem_index": None,

            "category":
                current_category,

            "difficulty_raw":
                None,

            "tags_raw": (
                [current_category]
                if current_category
                else []
            ),

            "stats_raw": {
                "solved_count":
                    solved,

                "attempted_count":
                    attempted,

                "acceptance_ratio":
                    acceptance_ratio,
            },

            "metadata_raw": {},
        })

    return output