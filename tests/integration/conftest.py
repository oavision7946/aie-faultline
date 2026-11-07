"""Fixtures for integration tests. These need the local stack (`make up`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline_core.config import AppSettings, SecretStore, load_settings

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="session")
def settings() -> AppSettings:
    return load_settings(config_dir=CONFIG_DIR)


@pytest.fixture(scope="session")
def secrets() -> SecretStore:
    return SecretStore.from_environment(CONFIG_DIR)
