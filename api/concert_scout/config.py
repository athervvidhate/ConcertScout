from pydantic import SecretStr
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
