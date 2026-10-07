"""Application configuration settings."""

from pathlib import Path
from typing import Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the Geospatial API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Geospatial File Measurement API"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000

    # Static assets
    static_dir: Path = Path(__file__).parent / "static"

    # File uploads
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = 50
    allowed_extensions: Set[str] = {".kml", ".zip"}

    # Database
    database_path: Path = Path("./data/geospatial.db")

    def ensure_directories(self) -> None:
        """Ensure necessary runtime directories exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
