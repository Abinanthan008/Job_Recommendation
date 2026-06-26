"""
Indeed Jobs MCP Server
-----------------------
An MCP (Model Context Protocol) server that exposes a tool for searching
job listings on Indeed, via the "Indeed12" API on RapidAPI
(host: indeed12.p.rapidapi.com).

Set the RAPIDAPI_KEY environment variable (or put it in a .env file next to
this script) before running.
"""

import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # picks up RAPIDAPI_KEY from a local .env file, if present

RAPIDAPI_HOST = "indeed12.p.rapidapi.com"
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_INDEED_KEY")
BASE_URL = f"https://{RAPIDAPI_HOST}/jobs/search"

mcp = FastMCP("indeed-jobs")


def _format_job(job: dict) -> str:
    """Best-effort formatting of a single job result.

    The Indeed12 API's exact field names can vary slightly between response
    versions, so we try a few likely keys for each piece of data and fall
    back gracefully if a field is missing.
    """
    title = job.get("job_title") or job.get("title") or job.get("position") or "Unknown title"
    company = job.get("company_name") or job.get("company") or "Unknown company"
    location = (
        job.get("location")
        or job.get("job_location")
        or job.get("formattedLocation")
        or "Not specified"
    )
    link = job.get("link") or job.get("job_url") or job.get("url") or job.get("apply_link") or ""
    salary = job.get("salary") or job.get("salary_text") or job.get("formattedSalary")
    posted = job.get("date") or job.get("formattedRelativeTime") or job.get("posted_at")
    rating = job.get("company_rating") or job.get("companyRating")

    lines = [f"**{title}** — {company}", f"Location: {location}"]
    if salary:
        lines.append(f"Salary: {salary}")
    if posted:
        lines.append(f"Posted: {posted}")
    if rating:
        lines.append(f"Company rating: {rating}")
    if link:
        lines.append(f"Link: {link}")
    return "\n".join(lines)


@mcp.tool()
async def search_indeed_jobs(
    job_title: str,
    location: str = "India",
    locality: str = "in",
    page: int = 1,
    radius: int = 50,
    sort: Optional[str] = None,
    fromage: Optional[int] = None,
) -> str:
    """Search Indeed for jobs matching a job title.

    Args:
        job_title: The job title or keyword to search for, e.g. "Data Analyst".
        location: City, state, or country to search in, e.g. "Austin, TX".
        locality: Country/marketplace code Indeed should search (e.g. "us",
            "gb", "ca", "in"). Must match the country of `location` or you'll
            get empty/irrelevant results.
        page: Page number of results, starting at 1. Each page returns up
            to ~15 jobs.
        radius: Search radius (miles) around the location.
        sort: Sort order. Leave unset for relevance (the API's default when
            this param is omitted); pass "date" to sort by most recent.
            Passing "relevance" explicitly is rejected by the API with a
            400 error, so we only send this param when it's "date".
        fromage: Only return jobs posted in the last N days (optional).
    """
    if not RAPIDAPI_KEY:
        return (
            "Error: RAPIDAPI_KEY is not set. Add it to your environment, or to a "
            ".env file next to server.py, then restart the server."
        )

    params = {
        "query": job_title,
        "location": location,
        "locality": locality,
        "page_id": str(page),
        "radius": str(radius),
    }
    if sort:
        params["sort"] = sort
    if fromage is not None:
        params["fromage"] = str(fromage)

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(BASE_URL, headers=headers, params=params)
    except httpx.RequestError as exc:
        return f"Error contacting Indeed API: {exc}"

    if response.status_code in (401, 403):
        return (
            "Error: RapidAPI rejected the request "
            f"(status {response.status_code}). Check that RAPIDAPI_KEY is correct "
            "and that your RapidAPI account is subscribed to the Indeed12 API."
        )
    if response.status_code == 429:
        return "Error: RapidAPI rate limit exceeded for your Indeed12 plan. Try again later or upgrade your plan."
    if response.status_code != 200:
        return f"Error: Indeed API returned status {response.status_code}: {response.text[:300]}"

    try:
        data = response.json()
    except ValueError:
        return "Error: Could not parse the Indeed API response as JSON."

    jobs = data.get("hits") or data.get("jobs") or []

    if not jobs:
        return f"No jobs found for '{job_title}' in '{location}'. Try a broader title or location."

    header = f"Found {len(jobs)} job(s) for '{job_title}' in '{location}' (page {page}):"
    body = "\n\n---\n\n".join(_format_job(job) for job in jobs)
    return f"{header}\n\n{body}"


if __name__ == "__main__":
    mcp.run()