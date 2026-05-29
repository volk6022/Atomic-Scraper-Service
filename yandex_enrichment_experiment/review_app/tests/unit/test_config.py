import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from review_app.config import Settings, get_settings


class TestDefaults:
    def test_defaults_are_sane(self):
        """Verify all default values match the specification."""
        settings = Settings(_env_file=None)

        assert settings.review_db_url == "postgresql+asyncpg://review:review@localhost:5432/review"
        assert settings.review_host == "127.0.0.1"
        assert settings.review_port == 8002
        assert settings.atomic_base_url == "http://localhost:8000"
        assert settings.atomic_api_key == "default_internal_key"
        assert settings.atomic_research_mode == "quality"
        assert settings.atomic_research_language == "ru"
        assert settings.atomic_poll_interval_s == 5.0
        assert settings.atomic_research_timeout_s == 1800
        assert settings.tts_device == "cpu"
        assert settings.tts_voice == "aidar"
        assert settings.tts_sample_rate == 48000
        assert settings.tts_model_language == "ru"
        assert settings.tts_model_name == "v3_1_ru"
        assert settings.list_page_size == 50
        assert settings.log_level == "INFO"

        # Path fields resolve correctly (use as_posix() for OS-agnostic checks)
        assert isinstance(settings.research_data_dir, Path)
        assert settings.research_data_dir.as_posix().endswith("data/research")
        assert isinstance(settings.orgs_file, Path)
        assert settings.orgs_file.name == "organizations_filtered.json"
        assert isinstance(settings.reviews_dir, Path)
        assert settings.reviews_dir.as_posix().endswith("data/reviews")


class TestEnvOverride:
    def test_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("REVIEW_PORT", "9999")
        monkeypatch.setenv("TTS_VOICE", "xenia")
        monkeypatch.setenv("ATOMIC_BASE_URL", "http://example.com")

        settings = Settings(_env_file=None)

        assert settings.review_port == 9999
        assert settings.tts_voice == "xenia"
        assert settings.atomic_base_url == "http://example.com"


class TestValidation:
    def test_tts_device_must_be_cpu(self):
        """Test that TTS_DEVICE=cuda raises ValidationError."""
        with pytest.raises(ValidationError):
            Settings(tts_device="cuda", _env_file=None)

    def test_tts_device_gpu_rejected(self):
        """Test that TTS_DEVICE=gpu is rejected."""
        with pytest.raises(ValidationError):
            Settings(tts_device="gpu", _env_file=None)

    def test_atomic_research_mode_literal(self):
        """Test that invalid ATOMIC_RESEARCH_MODE raises ValidationError."""
        with pytest.raises(ValidationError):
            Settings(atomic_research_mode="fast", _env_file=None)

    def test_atomic_research_mode_invalid_value(self):
        """Test that unknown mode value is rejected."""
        with pytest.raises(ValidationError):
            Settings(atomic_research_mode="unknown", _env_file=None)

    def test_valid_research_modes_accepted(self):
        """Test that valid modes are accepted."""
        for mode in ["speed", "balanced", "quality"]:
            settings = Settings(atomic_research_mode=mode, _env_file=None)
            assert settings.atomic_research_mode == mode


class TestCaching:
    def test_get_settings_is_cached(self):
        """Test that get_settings() returns the same object (cached)."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
