import pytest
from pydantic import ValidationError

from ragdesk.core.config import Environment, Settings


def _production(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "jwt_secret": "x" * 48,
        "embedder": "fake",
        "chat_model_provider": "fake",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def test_production_accepts_a_strong_secret() -> None:
    assert _production().environment.is_deployed


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _production(jwt_secret="change-me-in-production-please-32-bytes-min")


def test_production_requires_provider_keys() -> None:
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        _production(chat_model_provider="claude")
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        _production(embedder="gemini")


def test_production_forbids_private_url_fetching() -> None:
    with pytest.raises(ValidationError, match="URL_ALLOW_PRIVATE_HOSTS"):
        _production(url_allow_private_hosts=True)


def test_docs_are_off_when_deployed_unless_exposed() -> None:
    assert _production().docs_enabled is False
    assert _production(expose_docs=True).docs_enabled is True
    assert Settings(_env_file=None, environment=Environment.LOCAL).docs_enabled is True
