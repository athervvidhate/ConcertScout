"""Explicit, bounded organizer feasibility probe. Never imported by the production app."""

import argparse
import asyncio
import datetime as dt
import json
import os
import time
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from concert_scout.sources import eventbrite


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    eventbrite_token: SecretStr


async def probe(organizers: list[str], output: Path) -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    now = dt.datetime.now(dt.UTC)
    rows: list[eventbrite.Listing] = []
    timings: dict[str, float] = {}
    async with eventbrite.make_client(settings.eventbrite_token.get_secret_value()) as client:
        for organizer in organizers:
            began = time.perf_counter()
            rows.extend(await eventbrite.organizer_listings(client, organizer, now))
            timings[organizer] = round(time.perf_counter() - began, 3)
    body = {
        "captured_at": now.isoformat(),
        "organizer_seconds": timings,
        "listings": [row.model_dump(mode="json", exclude_none=True) for row in rows],
    }
    # No account metadata, request headers, token or full HTML descriptions are saved.
    output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        json.dump(body, file, indent=2)
        file.write("\n")
    print(
        json.dumps(
            {
                "listings": len(rows),
                "organizers": len(organizers),
                "structured_lineups": sum(bool(r.concert.artists) for r in rows),
                "organizer_seconds": timings,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organizer", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    organizers = list(dict.fromkeys(args.organizer))
    if len(organizers) > 5:
        parser.error("at most five organizers per explicit run")
    try:
        asyncio.run(probe(organizers, args.out))
    except eventbrite.EventbriteError as exc:
        parser.exit(1, f"Eventbrite probe failed: {exc}\n")


if __name__ == "__main__":
    main()
