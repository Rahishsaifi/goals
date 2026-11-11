from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
# Local `.env` only. Keep Azure connection secrets out of automatic load so local
# Postgres is not overridden by `.env.azure`. Foundry keys can live in `.env`.
_ENV_FILES = (
    str(_REPO_ROOT / ".env"),
    ".env",
)


class Settings(BaseSettings):
    app_env: Literal["local", "test", "poc"] = "local"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://recruitment:recruitment@localhost:5432/recruitment",
    )
    model_provider: Literal["mock", "foundry"] = "mock"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_translator_endpoint: str | None = None
    azure_translator_key: str | None = None
    azure_translator_region: str | None = None
    azure_translator_paid_endpoint: str | None = None
    azure_translator_paid_key: str | None = None
    azure_translator_paid_region: str | None = None
    # Skip the free Translator key entirely and send every batch to the paid key.
    azure_translator_paid_only: bool = False
    goals_localization_max_upload_mb: int = 50
    goals_localization_translate_batch_size: int = 50
    # Stay under the Translator F0 window of about 33,300 characters per minute.
    goals_localization_translator_chars_per_minute: int = 30000
    goals_localization_max_correction_attempts: int = 1
    # Foundry semantic review: parallel row requests and a tokens-per-minute ceiling kept
    # below the deployment quota.
    goals_foundry_concurrency: int = 24
    goals_foundry_tokens_per_minute: int = 600000
    session_cookie_name: str = "ri_session"
    csrf_cookie_name: str = "ri_csrf"
    csrf_header_name: str = "x-csrf-token"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    invitation_ttl_hours: int = 72
    password_reset_ttl_hours: int = 1
    email_verification_ttl_hours: int = 48
    min_password_length: int = 8

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
