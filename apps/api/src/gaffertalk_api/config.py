from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from GAFFERTALK-prefixed variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GAFFERTALK_",
        extra="ignore",
    )

    app_name: str = "GafferTalk API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    cors_origins: str = "http://localhost:3000"
    fpl_base_url: str = "https://fantasy.premierleague.com/api/"
    fpl_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    fpl_max_attempts: int = Field(default=3, ge=1, le=5)
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1/"
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=12.0, gt=0, le=30)
    free_question_limit: int = Field(default=3, ge=1, le=20)
    free_usage_database_path: Path = Path(".data/gaffertalk.sqlite3")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def deployment_configuration_is_safe(self) -> "Settings":
        if self.environment not in {"staging", "production"}:
            return self
        if not self.groq_api_key or not self.groq_api_key.strip():
            raise ValueError("staging and production require GAFFERTALK_GROQ_API_KEY")
        if not self.free_usage_database_path.is_absolute():
            raise ValueError(
                "staging and production require an absolute persistent usage database path"
            )
        if not self.allowed_origins:
            raise ValueError("staging and production require at least one CORS origin")
        for origin in self.allowed_origins:
            parsed = urlparse(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or "*" in origin
                or parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("staging and production CORS origins must be exact HTTPS origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
