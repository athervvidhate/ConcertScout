"""Store a vector for every Artist in the Catalog, from the same Redis the sync fills.

Needs GOOGLE_API_KEY, SUPABASE_URL and SUPABASE_SECRET_KEY in `.env`, plus the Catalog in Redis.
An Artist whose Sonic Card is unchanged is skipped, so a repeat run costs no embedding calls.
Gemini embeds at about $0.15 per million tokens and a card is about 80 tokens, so 50,000 Artists
cost under a dollar. Run it from `api/`:

    uv run python scripts/embed_artists.py --limit 500
    uv run python scripts/embed_artists.py --only-new
    uv run python scripts/embed_artists.py --artist "Four Tet" --artist "Floating Points"
"""

import argparse
import asyncio
import datetime as dt
import logging

from concert_scout import catalog, embeddings, telemetry
from concert_scout.app import make_services
from concert_scout.config import Settings
from concert_scout.models import Artist


async def main(names: list[str], limit: int | None, only_new: bool) -> int:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    services = make_services(settings)
    sources = services.embedding_sources()
    if sources is None:
        print("Set GOOGLE_API_KEY, SUPABASE_URL and SUPABASE_SECRET_KEY in api/.env first.")
        return 1
    try:
        if names:
            artists = [Artist(name=name) for name in names]
        else:
            artists = await catalog.all_artists(services.redis, dt.date.today())
        print(f"{len(artists)} Artists to look at")
        with telemetry.search() as usage:
            report = await embeddings.embed_artists(
                artists, sources, only_new=only_new, limit=limit
            )
        print(
            f"cards {report.card}, graph-propagated {report.graph}, unchanged {report.unchanged}, "
            f"no peers yet {report.unplaced}, looked up {report.looked_up}"
        )
        print(f"estimated embedding input: {usage.input_tokens} tokens, ${usage.cost:.4f}")
        if report.failed:
            print("Stopped early on an error. Run it again to continue.")
            return 1
        return 0
    finally:
        for client in (sources.supabase, sources.listenbrainz, sources.lastfm):
            if client:
                await client.aclose()
        await services.redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--artist", action="append", default=[], help="embed this name only")
    parser.add_argument("--limit", type=int, help="look up at most this many Artists")
    parser.add_argument("--only-new", action="store_true", help="skip Artists that have a vector")
    args = parser.parse_args()
    logging.getLogger(telemetry.__name__).setLevel(logging.ERROR)
    raise SystemExit(asyncio.run(main(args.artist, args.limit, args.only_new)))
