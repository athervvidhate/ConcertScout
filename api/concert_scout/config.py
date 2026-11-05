from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tm_key: SecretStr
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
