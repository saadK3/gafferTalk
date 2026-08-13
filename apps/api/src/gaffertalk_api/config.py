from functools import lru_cache

from pydantic import Field
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
    fpl_base_url: str = "https://fantasy.premierleague.com/api/"
    fpl_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    fpl_max_attempts: int = Field(default=3, ge=1, le=5)
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1/"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = Field(default=12.0, gt=0, le=30)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
