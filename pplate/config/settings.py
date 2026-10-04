"""Application settings, loaded from environment variables / `.env`."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "P-Plate Car Finder"
    app_description: str = (
        "Local tool to shortlist a safe, legal and affordable first car for a "
        "Victorian P1/P2 driver."
    )
    database_url: str = "sqlite:///./pplate.db"
    auto_create_tables: bool = True
    log_level: str = "INFO"

    # --- Victorian P-plate thresholds -------------------------------------
    pplate_power_to_mass_limit: float = 130.0
    pplate_borderline_lower: float = 120.0
    pplate_absolute_power_limit_kw: float | None = None

    # --- Web search --------------------------------------------------------
    tavily_api_key: str | None = None
    search_user_agent: str = "PPlateCarFinder/0.1 (+local educational use)"
    search_rate_limit_seconds: float = 2.0
    search_cache_ttl_seconds: int = 86400
    external_request_timeout_seconds: float = 20.0

    # --- Listing fetch -----------------------------------------------------
    listing_provider: str = "auto"
    listings_csv_path: str = "./data/listings.csv"
    listing_rate_limit_seconds: float = 3.0
    listing_cache_ttl_seconds: int = 3600
    cache_dir: str = "./.cache"

    # --- Locations ---------------------------------------------------------
    base_dir: str = "."


@lru_cache
def get_settings() -> Settings:
    return Settings()
