"""Application settings, loaded from environment variables (or a local .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All tunable values live here so nothing is hard-coded in the code base."""

    app_name: str = "Geospatial File Measurement API"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{(BASE_DIR / 'geospatial.db').as_posix()}"
    upload_dir: Path = BASE_DIR / "uploads"

    max_upload_size_mb: int = 20
    max_zip_entries: int = 100
    max_zip_uncompressed_mb: int = 200

    # Comma-separated list of browser origins allowed to call the API (never "*").
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_zip_uncompressed_bytes(self) -> int:
        return self.max_zip_uncompressed_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings object (also used as a FastAPI dependency)."""
    return Settings()
