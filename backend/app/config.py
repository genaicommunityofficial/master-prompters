from __future__ import annotations

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Prompt Competition Platform"
    environment: str = "development"

    # Supabase
    supabase_url: str
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Gemini (used by the evaluator; key is server-side only)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # Auth / JWT
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_minutes: int = 60 * 24  # 24h session

    # Admin login (username/password -> JWT with role=admin)
    admin_username: str = "admin"
    admin_password_hash: str = ""  # bcrypt hash; if empty, admin login disabled
    admin_codes: str = ""  # legacy: comma-separated allowed admin emails

    # Monitor / logging
    log_level: str = "INFO"
    request_log_enabled: bool = True
    monitor_bucket_seconds: int = 60  # RPS/latency window for admin monitor

    # CORS
    cors_origins: str = "*"

    # The event whose registrations we accept for QR login
    qr_event_id: str = ""

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()