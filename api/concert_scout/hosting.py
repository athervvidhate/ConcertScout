"""Vercel entrypoint settings: local defaults must never expose a public Search."""

from urllib.parse import urlsplit

from concert_scout.config import Settings


def validate_public_settings(settings: Settings) -> None:
    redis = urlsplit(settings.redis_url)
    if redis.scheme != "rediss" or not redis.hostname or not redis.password:
        raise ValueError("Public hosting requires REDIS_URL with TLS and a password")
    if not settings.cors_origins:
        raise ValueError("Public hosting requires exact HTTPS CORS_ORIGINS")
    for value in settings.cors_origins:
        origin = urlsplit(value)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.hostname in {"localhost", "127.0.0.1", "::1"}
            or "*" in value
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Public hosting requires exact HTTPS CORS_ORIGINS")
    secret = settings.turnstile_secret.get_secret_value()
    if not secret or secret in {f"{n}x0000000000000000000000000000000AA" for n in (1, 2, 3)}:
        raise ValueError("Public hosting requires a real TURNSTILE_SECRET")
    if settings.client_ip_header != "x-vercel-forwarded-for":
        raise ValueError("Vercel requires CLIENT_IP_HEADER=x-vercel-forwarded-for")
    if settings.spotify_client_id and urlsplit(settings.spotify_redirect_uri).scheme != "https":
        raise ValueError("Public Spotify connections require an HTTPS SPOTIFY_REDIRECT_URI")
