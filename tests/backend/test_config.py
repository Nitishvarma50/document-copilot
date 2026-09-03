"""Tests for backend settings and derived configuration."""

from app.config import settings


def test_settings_load_with_required_environment() -> None:
    # Settings are created at import time, so verify the application settings
    # object used by the backend.
    assert settings.database_url.startswith("postgresql")
    assert settings.cors_origins == ["http://localhost:5173"]


def test_default_model_configuration_is_present() -> None:
    assert settings.openai_embeddings_model
    assert settings.openai_chat_model
    assert settings.openai_grounding_model
    assert settings.openai_agent_request_limit > 0
