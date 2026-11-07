#!/usr/bin/env python3
"""Prove the hourly Search limit against a running API, at no model cost.

Each request carries a bot token no verifier accepts, so it is counted and then refused before any
model call. Each also forges the forwarding headers with a new address. A limit that trusted them
would never trip. The run spends this client's Searches for the current clock hour.

    python3 scripts/check_visitor_limit.py https://api.concertscout.app \
        --origin https://concertscout.app --limit 10
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

BAD_TOKEN = "visitor-limit-check"


def post(api: str, origin: str, attempt: int) -> tuple[int, dict[str, object]]:
    forged = f"203.0.113.{attempt}"
    request = urllib.request.Request(
        f"{api.rstrip('/')}/search",
        data=json.dumps({"text": "limit check", "token": BAD_TOKEN, "time_zone": "UTC"}).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            "User-Agent": "concert-scout-limit-check",
            "X-Forwarded-For": forged,
            "X-Vercel-Forwarded-For": forged,
            "X-Real-IP": forged,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, {}
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def check(api: str, origin: str, limit: int) -> str | None:
    """The first broken promise, or None when the limit held."""
    for attempt in range(1, limit + 2):
        status, body = post(api, origin, attempt)
        code = body.get("code", "")
        print(f"{attempt:>3}  {status}  {code}")
        if status == 200:
            return "The API accepted the bad token, so this run stopped before any more model calls."
        if status == 429 and code == "visitor_limit":
            if attempt <= limit:
                return f"Refused after {attempt - 1}. Run it again next clock hour or check the limit."
            return None if body.get("retry_after") else "The refusal gave no retry_after."
        if status == 503:
            return f"Search is unavailable here: {code}."
    return f"Request {limit + 1} was not refused, so the limit did not hold."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("api")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if failure := check(args.api, args.origin, args.limit):
        sys.exit(failure)
    print(f"The limit held at {args.limit}, and forged addresses did not reset it.")


if __name__ == "__main__":
    main()
