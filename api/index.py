"""Vercel loads this single FastAPI instance; local running uses the app factory."""

from concert_scout.app import create_app
from concert_scout.config import Settings
from concert_scout.hosting import validate_public_settings

settings = Settings()  # pyright: ignore[reportCallIssue]
validate_public_settings(settings)
app = create_app(settings)
