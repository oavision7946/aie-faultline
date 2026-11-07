"""Unit tests for the LLM provider registry schema and the offline check."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from faultline_core.config import ConfigError
from faultline_llm.check import check_llm_config, role_problems
from faultline_llm.config import LLMConfig, load_llm_config

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"

MODEL: dict[str, Any] = {
    "id": "hosted-a",
    "provider": "hosted",
    "model_name": "vendor-model-a",
    "roles": ["investigator"],
    "context_window": 100000,
    "capabilities": {"tool_calling": True, "structured_output": True},
    "defaults": {"max_output_tokens": 1000, "timeout_s": 60, "max_retries": 2},
    "pricing": {
        "input_per_mtok": "1.00",
        "output_per_mtok": "2.00",
        "effective_date": "2026-01-01",
    },
}
LOCAL_MODEL: dict[str, Any] = {
    **MODEL,
    "id": "local-a",
    "provider": "local",
    "pricing": {"input_per_mtok": "0", "output_per_mtok": "0", "effective_date": "2026-01-01"},
    "local": {"quantization": "8-bit", "serving_stack": "server"},
}
BASE: dict[str, Any] = {
    "providers": [
        {
            "name": "hosted",
            "type": "anthropic",
            "base_url": "https://api.example.com",
            "api_key_env": "HOSTED_KEY",
            "enabled_in": ["dev", "lab"],
        },
        {
            "name": "local",
            "type": "local_openai_compatible",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key_env": "LOCAL_KEY",
            "enabled_in": ["lab"],
        },
        {
            "name": "unused",
            "type": "openai",
            "base_url": "https://api.example.org/v1",
            "api_key_env": "UNUSED_KEY",
            "enabled_in": ["lab"],
        },
    ],
    "models": [MODEL, LOCAL_MODEL],
    "profiles": {"iterate": {"investigator": "hosted-a"}},
}


def make(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE)
    data.update(changes)
    return data


def test_valid_config_and_lookups() -> None:
    config = LLMConfig.model_validate(BASE)
    assert config.provider("local").type == "local_openai_compatible"
    assert config.model("hosted-a").pricing.input_per_mtok == 1
    assert [p.name for p in config.enabled_providers("dev")] == ["hosted"]
    assert config.resolve("iterate", "investigator").id == "hosted-a"
    assert [m.id for m in config.models_for("local")] == ["local-a"]
    with pytest.raises(KeyError):
        config.provider("missing")
    with pytest.raises(KeyError):
        config.model("missing")
    with pytest.raises(KeyError, match="no model for role"):
        config.resolve("iterate", "judge")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"models": [{**MODEL, "provider": "nope"}]}, "unknown provider"),
        ({"models": [MODEL, MODEL]}, "model ids must be unique"),
        ({"models": [{**LOCAL_MODEL, "local": None}]}, "need a 'local' block"),
        ({"models": [{**MODEL, "local": LOCAL_MODEL["local"]}]}, "only for local providers"),
        ({"profiles": {"p": {"judge": "ghost"}}}, "unknown 'ghost'"),
        ({"models": [{**MODEL, "roles": ["boss"]}]}, "roles"),
        ({"models": [{**MODEL, "extra": 1}]}, "extra"),
        ({"models": [{**MODEL, "id": "Has Spaces"}]}, "id"),
    ],
)
def test_invalid_configs(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        LLMConfig.model_validate(make(**changes))


def test_duplicate_provider_names() -> None:
    providers = [BASE["providers"][0], BASE["providers"][0]]
    with pytest.raises(ValidationError, match="provider names must be unique"):
        LLMConfig.model_validate(make(providers=providers, models=[], profiles={}))


def test_hosted_provider_needs_key_variable() -> None:
    provider = {**BASE["providers"][0], "api_key_env": None}
    with pytest.raises(ValidationError, match="api_key_env"):
        LLMConfig.model_validate(make(providers=[provider], models=[], profiles={}))


def test_check_reports_missing_keys_and_notes() -> None:
    config = LLMConfig.model_validate(BASE)
    reports = {r.provider: r for r in check_llm_config(config, "lab", lambda name: False)}
    assert not reports["hosted"].ok
    assert reports["hosted"].problems == ["HOSTED_KEY is not set"]
    assert reports["local"].ok  # key optional for local servers
    assert "optional" in reports["local"].notes[0]
    assert reports["unused"].notes[-1] == "no models declared"


def test_check_passes_when_keys_present() -> None:
    config = LLMConfig.model_validate(BASE)
    reports = check_llm_config(config, "dev", lambda name: name == "HOSTED_KEY")
    assert [r.ok for r in reports] == [True]


def test_role_capability_consistency() -> None:
    weak = {**MODEL, "roles": ["investigator", "judge"],
            "capabilities": {"tool_calling": False, "structured_output": False}}  # fmt: skip
    config = LLMConfig.model_validate(make(models=[weak]))
    problems = role_problems(config.model("hosted-a"))
    assert len(problems) == 3
    reports = check_llm_config(config, "dev", lambda name: True)
    assert not reports[0].ok


@pytest.mark.parametrize("environment", ["dev", "lab", "ci"])
def test_repository_providers_file_is_valid(environment: str) -> None:
    config = load_llm_config(environment=environment, config_dir=REPO_CONFIG)
    assert config.resolve("reference", "investigator").provider == "anthropic"
    for model in config.models:
        assert role_problems(model) == []


def test_loader_reports_validation_errors(tmp_path: Path) -> None:
    (tmp_path / "app.yaml").write_text("")
    (tmp_path / "llm").mkdir()
    (tmp_path / "llm" / "providers.yaml").write_text("providers: []\nbogus: 1\n")
    with pytest.raises(ConfigError, match="bogus"):
        load_llm_config(environment="dev", config_dir=tmp_path)
