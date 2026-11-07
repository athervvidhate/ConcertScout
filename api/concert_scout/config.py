import ipaddress
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from concert_scout import limits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tm_key: SecretStr
    anthropic_api_key: SecretStr
    geoapify_key: SecretStr
    lastfm_key: SecretStr | None = None
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    search_enabled: bool = True
    searches_per_hour: int = limits.SEARCHES_PER_HOUR
    # Cloudflare's published always-pass test secret. A public deployment must replace it.
    turnstile_secret: SecretStr = SecretStr("1x0000000000000000000000000000000AA")
    client_ip_header: str | None = None

    resend_api_key: SecretStr | None = None
    feedback_email: str | None = None

    spotify_client_id: str | None = None
    spotify_client_secret: SecretStr | None = None
    spotify_encryption_key: SecretStr | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"

    @field_validator("spotify_redirect_uri")
    @classmethod
    def safe_spotify_redirect(cls, value: str) -> str:
        uri = urlsplit(value)
        if uri.scheme == "http":
            try:
                loopback = ipaddress.ip_address(uri.hostname or "").is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ValueError("Spotify HTTP redirects require a loopback IP literal")
        elif uri.scheme != "https":
            raise ValueError("Spotify redirects require HTTPS")
        if uri.path != "/auth/spotify/callback" or uri.query or uri.fragment:
            raise ValueError("Spotify redirect must point to /auth/spotify/callback")
        return value
