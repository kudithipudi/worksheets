"""
Application configuration for the Texas Worksheet Generator.
All settings are loaded from environment variables / `.env` via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── OpenRouter / LLM ────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    llm_model: str = "qwen/qwen3-vl-30b-a3b-thinking"
    site_url: str = "http://localhost"

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/worksheets.db"

    # ── Hybrid-sourcing threshold: use DB when >= N vetted questions exist ──
    vetted_threshold: int = 1000

    # ── Subpath deployment (behind nginx at /worksheets/) ──────────────────
    # NOTE: nginx's /worksheets/ location rewrites the prefix off the path
    # before proxying (rewrite ^/worksheets(/.*)$ $1 break;), so the app
    # receives unprefixed paths. Templates therefore use relative asset URLs
    # (./static/...) rather than FastAPI's root_path/url_for mechanism —
    # passing root_path to the FastAPI() constructor here would make
    # Starlette expect the prefix to still be present on incoming requests,
    # which breaks the /static Mount. Kept for documentation/parity only.
    root_path: str = ""


settings = Settings()
