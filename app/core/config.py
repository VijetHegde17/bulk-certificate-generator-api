from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    APP_NAME: str = "Bulk Certificate Generator API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Database: SQLite default for local development, easily overridden with PostgreSQL
    DATABASE_URL: str = "sqlite:///./certificates.db"

    # Directory for generated PDF certificates
    GENERATED_CERTIFICATES_DIR: str = "generated_certificates"

    # Directory for templates (if applicable)
    TEMPLATES_DIR: str = "templates"

    # Maximum recipients permitted in a single bulk request
    MAX_BULK_LIMIT: int = 1000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def certificates_dir_path(self) -> Path:
        """Returns the resolved absolute path to the certificates storage directory."""
        path = Path(self.GENERATED_CERTIFICATES_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
