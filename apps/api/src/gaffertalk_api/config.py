from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from GAFFERTALK-prefixed variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GAFFERTALK_",
        extra="ignore",
    )

    app_name: str = "GafferTalk API"
    environment: str = "development"
    cors_origins: str = "http://localhost:3000"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
