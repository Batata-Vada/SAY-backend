import time
import requests


URL = "https://leetcode.com/graphql"


QUERY = """
query problemsetQuestionListV2(
    $filters: QuestionFilterInput
    $limit: Int
    $searchKeyword: String
    $skip: Int
    $sortBy: QuestionSortByInput
    $categorySlug: String
) {
    problemsetQuestionListV2(
        filters: $filters
        limit: $limit
        searchKeyword: $searchKeyword
        skip: $skip
        sortBy: $sortBy
        categorySlug: $categorySlug
    ) {
        questions {
            id
            titleSlug
            title
            questionFrontendId
            paidOnly
            difficulty

            topicTags {
                name
                slug
            }

            acRate
        }

        totalLength
        hasMore
    }
}
"""


HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",

    "Origin": "https://leetcode.com",

    "Referer": (
        "https://leetcode.com/problemset/"
    ),

    # Don't identify as the requests library.
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/130.0.0.0 "
        "Safari/537.36"
    ),
}


def fetch_leetcode_page(
    skip,
    limit=100,
):
    payload = {
        "operationName":
            "problemsetQuestionListV2",

        "variables": {
            "filters": {
                "filterCombineType":
                    "ALL",
            },

            "limit":
                limit,

            "searchKeyword":
                "",

            "skip":
                skip,

            "sortBy": {
                "sortField":
                    "CUSTOM",

                "sortOrder":
                    "ASCENDING",
            },

            "categorySlug":
                "all-code-essentials",
        },

        "query":
            QUERY,
    }

    response = requests.post(
        URL,
        json=payload,
        headers=HEADERS,
        timeout=30,
    )

    #
    # VERY useful while debugging LeetCode.
    #
    if not response.ok:
        print(
            "[leetcode] status:",
            response.status_code,
        )

        print(
            "[leetcode] response:",
            response.text[:2000],
        )

        raise RuntimeError(
            f"LeetCode returned "
            f"HTTP {response.status_code}"
        )

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(
            "LeetCode GraphQL error: "
            f"{data['errors']}"
        )

    result = data.get(
        "data",
        {},
    ).get(
        "problemsetQuestionListV2"
    )

    if result is None:
        raise RuntimeError(
            "LeetCode returned no "
            "problemsetQuestionListV2"
        )

    return result


def fetch_leetcode_problems():
    output = []

    skip = 0
    limit = 100

    while True:
        print(
            f"[leetcode] fetching "
            f"{skip} - {skip + limit}"
        )

        page = fetch_leetcode_page(
            skip=skip,
            limit=limit,
        )

        questions = page.get(
            "questions",
            [],
        )

        for question in questions:
            output.append({
                "platform":
                    "LEETCODE",

                "external_id":
                    question[
                        "questionFrontendId"
                    ],

                "title":
                    question["title"],

                "slug":
                    question["titleSlug"],

                "url": (
                    "https://leetcode.com/"
                    "problems/"
                    f"{question['titleSlug']}/"
                ),

                "contest_id":
                    None,

                "problem_index":
                    None,

                "category":
                    None,

                "difficulty_raw": {
                    "label":
                        question[
                            "difficulty"
                        ],
                },

                "tags_raw": [
                    tag["name"]
                    for tag
                    in question.get(
                        "topicTags",
                        [],
                    )
                ],

                "stats_raw": {
                    "acceptance_rate":
                        question.get(
                            "acRate"
                        ),
                },

                "metadata_raw": {
                    "leetcode_internal_id":
                        question.get("id"),

                    "paid_only":
                        question.get(
                            "paidOnly",
                            False,
                        ),
                },
            })

        print(
            f"[leetcode] received "
            f"{len(questions)} "
            f"(total collected: "
            f"{len(output)})"
        )

        if not page.get(
            "hasMore",
            False,
        ):
            break

        skip += limit

        #
        # Don't hammer an undocumented API.
        #
        time.sleep(1)

    return output