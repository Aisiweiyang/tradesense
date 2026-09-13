"""Application configuration loaded from environment / .env file.

Secrets are never stored in the repository; see .env.example at project root.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TradeSense"
    environment: str = "local"

    # Database: SQLite for local one-click start, PostgreSQL for production.
    database_url: str = "sqlite:///./tradesense.db"

    # Auth
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"

    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]

    # Optional AI layer: none | openai_compat | ollama
    ai_provider: str = "none"
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ai_timeout_seconds: int = 25
    ai_max_retries: int = 1

    # Uploads
    upload_max_mb: int = 10
    upload_dir: str = "./uploads"

    # Quotation defaults (overridable per organization in settings UI)
    default_margin_rate: float = 0.15
    quote_valid_days: int = 30
    exchange_rate_buffer: float = 0.02

    # Demo data
    seed_demo_data: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
