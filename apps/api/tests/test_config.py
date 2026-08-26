import pytest
from pydantic import ValidationError

from gaffertalk_api.config import Settings


def deployment_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "staging",
        "cors_origins": "https://staging.gaffertalk.com",
        "groq_api_key": "test-only-key",
        "free_usage_database_path": "/data/gaffertalk.sqlite3",
        "database_url": "postgresql://example.invalid/gaffertalk",
        "supabase_url": "https://example.supabase.co",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_staging_configuration_accepts_exact_https_origins_and_persistent_path() -> None:
    settings = deployment_settings(
        cors_origins="https://gaffertalk.com, https://www.gaffertalk.com"
    )

    assert settings.allowed_origins == [
        "https://gaffertalk.com",
        "https://www.gaffertalk.com",
    ]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"groq_api_key": ""}, "GAFFERTALK_GROQ_API_KEY"),
        ({"free_usage_database_path": ".data/usage.sqlite3"}, "absolute persistent"),
        ({"database_url": ""}, "GAFFERTALK_DATABASE_URL"),
        ({"supabase_url": "http://example.supabase.co"}, "HTTPS GAFFERTALK_SUPABASE_URL"),
        ({"cors_origins": "http://localhost:3000"}, "exact HTTPS origins"),
        ({"cors_origins": "https://*.gaffertalk.com"}, "exact HTTPS origins"),
        ({"cors_origins": "https://gaffertalk.com/recommend"}, "exact HTTPS origins"),
    ],
)
def test_unsafe_deployment_configuration_fails_fast(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        deployment_settings(**overrides)


def test_development_keeps_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.allowed_origins == ["http://localhost:3000"]
    assert settings.free_usage_database_path.as_posix() == ".data/gaffertalk.sqlite3"
