"""Application settings, loaded from environment variables (and .env in local dev)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the PowerDNS adapter.

    Every field has a default so importing the app never fails; real values
    come from the environment (PDNS_API_URL, PDNS_API_KEY, ...).
    """

    pdns_api_url: str = "http://pdns:8081/api/v1"
    pdns_api_key: str = ""
    pdns_server_id: str = "localhost"
    cors_origins: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
