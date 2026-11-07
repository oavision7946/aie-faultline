"""Unit tests for the configuration and secrets loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline_core.config import (
    CONFIG_DIR_ENV_VAR,
    ENVIRONMENT_ENV_VAR,
    AppSettings,
    ConfigError,
    MissingSecretError,
    SecretStore,
    StrictModel,
    deep_merge,
    find_config_dir,
    layer_paths,
    load_config,
    load_settings,
    process_environment,
    read_selected_environment,
    resolve_environment,
    write_selected_environment,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENVIRONMENT_ENV_VAR, raising=False)
    monkeypatch.delenv(CONFIG_DIR_ENV_VAR, raising=False)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    cdir = tmp_path / "config"
    (cdir / "environments").mkdir(parents=True)
    (cdir / "app.yaml").write_text("clickhouse:\n  http_port: 8123\n  memory_limit: 4g\n")
    (cdir / "environments" / "lab.yaml").write_text("clickhouse:\n  memory_limit: 24g\n")
    return cdir


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# -- settings layering ------------------------------------------------------


def test_defaults_and_environment(config_dir: Path) -> None:
    settings = load_settings(config_dir=config_dir)
    assert settings.environment == "dev"
    assert settings.clickhouse.memory_limit == "4g"
    assert settings.bind_host == "127.0.0.1"


def test_environment_overlay_applies(config_dir: Path) -> None:
    settings = load_settings(environment="lab", config_dir=config_dir)
    assert settings.clickhouse.memory_limit == "24g"
    assert settings.clickhouse.http_port == 8123  # merged, not replaced


def test_local_overlay_wins(config_dir: Path) -> None:
    write(
        config_dir / "local" / "app.yaml", "bind_host: 10.0.0.5\nclickhouse:\n  http_port: 18123\n"
    )
    settings = load_settings(environment="lab", config_dir=config_dir)
    assert settings.bind_host == "10.0.0.5"
    assert settings.clickhouse.http_port == 18123
    assert settings.clickhouse.memory_limit == "24g"


def test_unknown_key_is_rejected(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "clickhouse:\n  http_prot: 1\n")
    with pytest.raises(ConfigError, match=r"clickhouse\.http_prot"):
        load_settings(config_dir=config_dir)


def test_invalid_value_is_rejected(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "clickhouse:\n  http_port: 70000\n")
    with pytest.raises(ConfigError, match="http_port"):
        load_settings(config_dir=config_dir)


def test_environment_key_cannot_be_set_in_yaml(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "environment: lab\n")
    with pytest.raises(ConfigError, match="derived"):
        load_settings(config_dir=config_dir)


def test_invalid_yaml(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "a: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_settings(config_dir=config_dir)


def test_top_level_must_be_mapping(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "- a\n- b\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_settings(config_dir=config_dir)


def test_empty_file_uses_defaults(config_dir: Path) -> None:
    write(config_dir / "app.yaml", "# nothing\n")
    assert load_settings(config_dir=config_dir).clickhouse.http_port == 8123


def test_missing_base_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Missing configuration file"):
        load_settings(config_dir=tmp_path)


def test_stack_secret_names(config_dir: Path) -> None:
    names = load_settings(config_dir=config_dir).stack_secret_names()
    assert names == ("CLICKHOUSE_WRITER_PASSWORD", "CLICKHOUSE_READONLY_PASSWORD")


# -- generic config files ---------------------------------------------------


class Thing(StrictModel):
    name: str
    size: int = 1


def test_load_config_with_overlays(config_dir: Path) -> None:
    write(config_dir / "things" / "thing.yaml", "name: base\nsize: 2\n")
    write(config_dir / "things" / "thing.ci.yaml", "size: 3\n")
    write(config_dir / "local" / "things" / "thing.yaml", "name: mine\n")
    thing = load_config("things/thing.yaml", Thing, environment="ci", config_dir=config_dir)
    assert thing == Thing(name="mine", size=3)


def test_layer_paths_rejects_escape(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="relative"):
        layer_paths(config_dir, "../secrets.yaml", "dev")
    with pytest.raises(ConfigError, match="relative"):
        layer_paths(config_dir, "/etc/passwd", "dev")


def test_deep_merge() -> None:
    base = {"a": {"b": 1, "c": 2}, "d": [1, 2]}
    assert deep_merge(base, {"a": {"c": 3}, "d": [9]}) == {"a": {"b": 1, "c": 3}, "d": [9]}
    assert base["a"] == {"b": 1, "c": 2}  # input is not mutated


# -- environment selection --------------------------------------------------


def test_environment_resolution_order(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_environment(config_dir) == "dev"
    assert read_selected_environment(config_dir) is None
    write_selected_environment(config_dir, "lab")
    assert read_selected_environment(config_dir) == "lab"
    assert resolve_environment(config_dir) == "lab"
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "ci")
    assert resolve_environment(config_dir) == "ci"
    assert resolve_environment(config_dir, "dev") == "dev"


def test_unknown_environment(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="Unknown environment"):
        write_selected_environment(config_dir, "prod")
    with pytest.raises(ConfigError, match="Unknown environment"):
        load_settings(environment="prod", config_dir=config_dir)


def test_find_config_dir_walks_up(config_dir: Path) -> None:
    nested = config_dir.parent / "a" / "b"
    nested.mkdir(parents=True)
    assert find_config_dir(nested) == config_dir


def test_find_config_dir_override(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(config_dir))
    assert find_config_dir(Path("/")) == config_dir
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(config_dir.parent))
    with pytest.raises(ConfigError, match=CONFIG_DIR_ENV_VAR):
        find_config_dir()


def test_find_config_dir_not_found(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Could not find"):
        find_config_dir(tmp_path)


def test_process_environment_is_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULTLINE_TEST_VALUE", "1")
    env = process_environment()
    env["FAULTLINE_TEST_VALUE"] = "2"
    assert process_environment()["FAULTLINE_TEST_VALUE"] == "1"


# -- secrets ----------------------------------------------------------------


def test_missing_secret_names_variable_not_value() -> None:
    store = SecretStore({"PRESENT": "s3cr3t-value", "EMPTY": ""})
    with pytest.raises(MissingSecretError) as info:
        store.require_all(["PRESENT", "EMPTY", "ABSENT"])
    message = str(info.value)
    assert "ABSENT" in message and "EMPTY" in message
    assert "s3cr3t-value" not in message
    assert info.value.names == ("ABSENT", "EMPTY")


def test_secret_values_are_masked() -> None:
    store = SecretStore({"KEY": "s3cr3t-value"})
    secret = store.require("KEY")
    assert "s3cr3t-value" not in repr(secret) and "s3cr3t-value" not in str(secret)
    assert secret.get_secret_value() == "s3cr3t-value"
    assert store.has("KEY") and not store.has("OTHER")
    assert store.get("OTHER") is None


def test_process_environment_overrides_dotenv(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (config_dir.parent / ".env").write_text("FROM_FILE=file\nBOTH=file\n")
    monkeypatch.setenv("BOTH", "process")
    monkeypatch.delenv("FROM_FILE", raising=False)
    store = SecretStore.from_environment(config_dir)
    assert store.require("FROM_FILE").get_secret_value() == "file"
    assert store.require("BOTH").get_secret_value() == "process"


def test_from_environment_without_dotenv(config_dir: Path) -> None:
    assert isinstance(SecretStore.from_environment(config_dir), SecretStore)


# -- the committed configuration -------------------------------------------


@pytest.mark.parametrize("environment", ["dev", "lab", "ci"])
def test_repository_settings_are_valid(environment: str) -> None:
    settings = load_settings(environment=environment, config_dir=REPO_ROOT / "config")
    assert isinstance(settings, AppSettings)
    assert settings.environment == environment
