"""Collect Codeforces problem metadata (no submission/judging logic here)."""

import logging

import requests
from flask import current_app

API_URL = "https://codeforces.com/api/problemset.problems"
PLATFORM = "CODEFORCES"
logger = logging.getLogger(__name__)


class CodeforcesCatalogError(RuntimeError):
    """The public catalog could not be downloaded or parsed safely."""


def _problem_key(item):
    """Unambiguously match a problem to its Codeforces statistics row."""
    return (
        item.get("contestId"),
        item.get("problemsetName"),
        item.get("index"),
    )


def fetch_codeforces_problems():
    """Fetch and normalize Codeforces programming problems.

    Never invent identities for problems missing both contestId and
    problemsetName. Those are skipped with an explicit warning.
    On any API/format failure, raise instead of returning an empty catalog.
    """
    timeout = current_app.config.get("CODEFORCES_TIMEOUT_SECONDS", 30)

    try:
        response = requests.get(
            API_URL,
            timeout=timeout,
            headers={"User-Agent": "SAY/1.0 (Codeforces catalog sync)"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CodeforcesCatalogError(
            "Unable to fetch a valid Codeforces catalog response"
        ) from exc

    if not isinstance(payload, dict) or payload.get("status") != "OK":
        comment = payload.get("comment", "unknown error") if isinstance(payload, dict) else "invalid response"
        raise CodeforcesCatalogError(f"Codeforces API failed: {comment}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise CodeforcesCatalogError("Codeforces response has no result object")

    raw_problems = result.get("problems")
    raw_statistics = result.get("problemStatistics")

    if (not isinstance(raw_problems, list) or not raw_problems
            or not isinstance(raw_statistics, list)):
        raise CodeforcesCatalogError("Codeforces returned an incomplete or empty problem catalog")

    statistics = {}
    for item in raw_statistics:
        if isinstance(item, dict):
            statistics[_problem_key(item)] = item

    normalized = []
    for item in raw_problems:
        if not isinstance(item, dict):
            raise CodeforcesCatalogError("Invalid problem entry in Codeforces response")

        # The field can be omitted by Codeforces; reject only explicit non-programming types.
        if item.get("type", "PROGRAMMING") != "PROGRAMMING":
            continue

        index = item.get("index")
        name = item.get("name")
        contest_id = item.get("contestId")
        problemset_name = item.get("problemsetName")

        if not isinstance(index, str) or not index or not isinstance(name, str) or not name:
            raise CodeforcesCatalogError("Programming problem has an invalid name or index")

        if contest_id is not None:
            if not isinstance(contest_id, int) or isinstance(contest_id, bool):
                raise CodeforcesCatalogError("Invalid Codeforces contestId")
            external_id = f"{contest_id}:{index}"
            url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        elif isinstance(problemset_name, str) and problemset_name.strip():
            external_id = f"{problemset_name}:{index}"
            # No universal contest URL for problemsets lacking contestId.
            url = "https://codeforces.com/problemset"
        else:
            logger.warning(
                "Skipping Codeforces problem with no stable identifier: %s (%s)",
                name, index
            )
            continue

        tags = item.get("tags", [])
        rating = item.get("rating")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise CodeforcesCatalogError(f"Invalid tags for {external_id}")
        if rating is not None and (not isinstance(rating, int) or isinstance(rating, bool)):
            raise CodeforcesCatalogError(f"Invalid rating for {external_id}")

        stat = statistics.get(_problem_key(item), {})
        normalized.append({
            "platform": PLATFORM,
            "external_id": external_id,
            "title": name,
            "slug": None,
            "url": url,
            "contest_id": str(contest_id) if contest_id is not None else None,
            "problem_index": index,
            "category": None,
            "difficulty_raw": {"rating": rating} if rating is not None else None,
            "tags_raw": tags,
            "stats_raw": {"solved_count": stat.get("solvedCount")},
            "metadata_raw": {
                "points": item.get("points"),
                "problemset_name": problemset_name,
            },
        })

    if not normalized:
        raise CodeforcesCatalogError("No identifiable Codeforces programming problems found")

    logger.info("Normalized %s Codeforces programming problems", len(normalized))
    return normalized