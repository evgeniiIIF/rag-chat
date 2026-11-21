"""Тесты настроек: env -> Settings, обязательный ключ, дефолты."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from core.config import Settings


def test_settings_reads_env_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_API_KEY", "test-key")
    monkeypatch.delenv("BACKEND_DATA_DIR", raising=False)

    settings = Settings()

    assert settings.api_key.get_secret_value() == "test-key"
    assert settings.retriever_k == 3
    assert settings.score_threshold == 0.35
    assert settings.data_dir.parent.name == "backend"


def test_settings_requires_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # без .env: ключа нет нигде

    with pytest.raises(ValidationError):
        Settings()


def test_settings_overrides_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_API_KEY", "k")
    monkeypatch.setenv("BACKEND_RETRIEVER_K", "5")
    monkeypatch.setenv("BACKEND_SCORE_THRESHOLD", "0.5")

    settings = Settings()

    assert settings.retriever_k == 5
    assert settings.score_threshold == 0.5


def test_qualification_defaults_follow_document() -> None:
    settings = Settings(api_key=SecretStr("test"))

    assert settings.min_debt_rub == 350_000
    assert settings.excluded_region_list == ("чечня", "днр", "лнр", "владимирская")
