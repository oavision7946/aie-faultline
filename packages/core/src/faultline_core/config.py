"""Configuration and secrets loading.

This module is the only place in the code base that reads configuration files or
environment variables. Every other component receives typed, validated objects
from here.

Layering for a configuration file ``config/<path>``:

1. the base file, ``config/<path>``;
2. an optional environment overlay. For ``app.yaml`` this is
   ``config/environments/<env>.yaml``; for any other file it is
   ``config/<dir>/<stem>.<env>.yaml``;
3. an optional machine-local overlay, ``config/local/<path>``. The
   ``config/local/`` folder is git-ignored and holds host-specific values
   (for example a bind address) that must not be committed.

Mappings are merged recursively; any other value in a later layer replaces the
earlier one. Unknown keys are rejected by the Pydantic models.

Secrets are never stored in YAML. YAML names the environment variable that holds
a secret, and :class:`SecretStore` resolves it from the process environment,
falling back to the repository's ``.env`` file. Process variables take precedence.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

__all__ = [
    "CONFIG_DIR_ENV_VAR",
    "ENVIRONMENTS",
    "ENVIRONMENT_ENV_VAR",
    "AppSettings",
    "CapacitySettings",
    "ClickHouseSettings",
    "ConfigError",
    "Environment",
    "MissingSecretError",
    "PathsSettings",
    "PostgresSettings",
    "ReadonlyQueryLimits",
    "SecretStore",
    "StrictModel",
    "deep_merge",
    "find_config_dir",
    "layer_paths",
    "load_config",
    "load_settings",
    "process_environment",
    "read_selected_environment",
    "resolve_environment",
    "write_selected_environment",
]

Environment = Literal["dev", "lab", "ci"]
ENVIRONMENTS: tuple[Environment, ...] = get_args(Environment)

CONFIG_DIR_ENV_VAR = "FAULTLINE_CONFIG_DIR"
ENVIRONMENT_ENV_VAR = "FAULTLINE_ENV"
_STATE_DIR = ".faultline"
_STATE_FILE = "env"
_DEFAULT_ENVIRONMENT: Environment = "dev"

Port = int


class ConfigError(Exception):
    """Raised when configuration is missing, malformed or invalid."""


class MissingSecretError(ConfigError):
    """Raised when required secrets are absent. The message names variables, never values."""

    def __init__(self, names: Iterable[str]) -> None:
        self.names = tuple(sorted(set(names)))
        joined = ", ".join(self.names)
        super().__init__(
            f"Missing required secret(s): {joined}. "
            "Set them in the environment or in the repository's .env file (see .env.example)."
        )


class StrictModel(BaseModel):
    """Base model for configuration: unknown keys are errors and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadonlyQueryLimits(StrictModel):
    """Query limits applied to the read-only ClickHouse user."""

    max_execution_time_s: int = Field(30, gt=0)
    max_result_rows: int = Field(100_000, gt=0)
    max_rows_to_read: int = Field(500_000_000, gt=0)
    max_memory_usage_bytes: int = Field(4 * 1024**3, gt=0)


class ClickHouseSettings(StrictModel):
    """Connection and container settings for ClickHouse."""

    image: str = "clickhouse/clickhouse-server:26.3"
    host: str = "127.0.0.1"
    http_port: Port = Field(8123, ge=1, le=65535)
    native_port: Port = Field(9000, ge=1, le=65535)
    database: str = Field("faultline", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    memory_limit: str = Field("4g", pattern=r"^\d+[kmg]$")
    writer_user: str = "faultline_writer"
    readonly_user: str = "faultline_readonly"
    writer_password_env: str = "CLICKHOUSE_WRITER_PASSWORD"
    readonly_password_env: str = "CLICKHOUSE_READONLY_PASSWORD"
    readonly_limits: ReadonlyQueryLimits = ReadonlyQueryLimits()


class PostgresSettings(StrictModel):
    """Connection settings for the operational Postgres database."""

    host: str = "127.0.0.1"
    port: Port = Field(54322, ge=1, le=65535)
    shadow_port: Port = Field(54320, ge=1, le=65535)
    database: str = "postgres"
    user_env: str = "POSTGRES_USER"
    password_env: str = "POSTGRES_PASSWORD"
    # The local Postgres stack publishes ports on bind_host. Starting it with a
    # wildcard bind_host, or with ports published on every interface, is refused
    # unless this is true.
    allow_wildcard_bind: bool = False


class PathsSettings(StrictModel):
    """Filesystem locations. Relative paths are resolved against the repository root."""

    data_dir: Path = Path("data")


class CapacitySettings(StrictModel):
    """Thresholds used by the capacity check."""

    min_free_disk_gb: float = Field(20.0, ge=0)
    max_clickhouse_memory_fraction: float = Field(0.5, gt=0, le=1)


class AppSettings(StrictModel):
    """Top-level application settings, from ``config/app.yaml`` plus overlays."""

    environment: Environment
    bind_host: str = "127.0.0.1"
    paths: PathsSettings = PathsSettings()
    clickhouse: ClickHouseSettings = ClickHouseSettings()
    postgres: PostgresSettings = PostgresSettings()
    capacity: CapacitySettings = CapacitySettings()

    def stack_secret_names(self) -> tuple[str, ...]:
        """Environment variable names the local service stack needs."""
        return (
            self.clickhouse.writer_password_env,
            self.clickhouse.readonly_password_env,
        )


# ---------------------------------------------------------------------------
# Locating configuration and choosing the environment
# ---------------------------------------------------------------------------


def process_environment() -> dict[str, str]:
    """Return a copy of the process environment (for example to pass to a subprocess)."""
    return dict(os.environ)


def find_config_dir(start: Path | None = None) -> Path:
    """Find the ``config/`` directory.

    Uses ``FAULTLINE_CONFIG_DIR`` when set; otherwise walks up from ``start``
    (default: the current directory) looking for ``config/app.yaml``.
    """
    override = os.environ.get(CONFIG_DIR_ENV_VAR)
    if override:
        path = Path(override).expanduser().resolve()
        if not (path / "app.yaml").is_file():
            raise ConfigError(f"{CONFIG_DIR_ENV_VAR} points to {path}, which has no app.yaml")
        return path
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config" / "app.yaml").is_file():
            return candidate / "config"
    raise ConfigError("Could not find config/app.yaml in this directory or any parent")


def _state_file(config_dir: Path) -> Path:
    return config_dir.parent / _STATE_DIR / _STATE_FILE


def _validate_environment(name: str) -> Environment:
    for env in ENVIRONMENTS:
        if env == name:
            return env
    raise ConfigError(f"Unknown environment {name!r}; expected one of {', '.join(ENVIRONMENTS)}")


def read_selected_environment(config_dir: Path) -> Environment | None:
    """Return the environment stored by ``env use``, if any."""
    state = _state_file(config_dir)
    if not state.is_file():
        return None
    return _validate_environment(state.read_text(encoding="utf-8").strip())


def write_selected_environment(config_dir: Path, name: str) -> Environment:
    """Persist the selected environment for this working copy (git-ignored)."""
    env = _validate_environment(name)
    state = _state_file(config_dir)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(env + "\n", encoding="utf-8")
    return env


def resolve_environment(config_dir: Path, explicit: str | None = None) -> Environment:
    """Pick the environment: argument, then ``FAULTLINE_ENV``, then ``env use``, then dev."""
    if explicit:
        return _validate_environment(explicit)
    from_env = os.environ.get(ENVIRONMENT_ENV_VAR)
    if from_env:
        return _validate_environment(from_env)
    return read_selected_environment(config_dir) or _DEFAULT_ENVIRONMENT


# ---------------------------------------------------------------------------
# Reading and merging YAML
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Merge ``overlay`` into ``base`` recursively; non-mapping values are replaced."""
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def layer_paths(config_dir: Path, relative: str, environment: Environment) -> list[Path]:
    """Return the base, environment-overlay and local-overlay paths for a config file."""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ConfigError(f"Configuration path must be relative to config/: {relative}")
    if rel == Path("app.yaml"):
        env_overlay = config_dir / "environments" / f"{environment}.yaml"
    else:
        env_overlay = config_dir / rel.parent / f"{rel.stem}.{environment}{rel.suffix}"
    return [config_dir / rel, env_overlay, config_dir / "local" / rel]


def _merged_layers(config_dir: Path, relative: str, environment: Environment) -> dict[str, Any]:
    base, *overlays = layer_paths(config_dir, relative, environment)
    if not base.is_file():
        raise ConfigError(f"Missing configuration file: {base}")
    data = _load_yaml(base)
    for path in overlays:
        if path.is_file():
            data = deep_merge(data, _load_yaml(path))
    return data


def _validate[M: BaseModel](model: type[M], data: Mapping[str, Any], source: str) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigError(f"{source}: {problems}") from exc


def load_config[M: BaseModel](
    relative: str,
    model: type[M],
    *,
    environment: str | None = None,
    config_dir: Path | None = None,
) -> M:
    """Load ``config/<relative>`` with its overlays and validate it against ``model``."""
    cdir = config_dir or find_config_dir()
    env = resolve_environment(cdir, environment)
    return _validate(model, _merged_layers(cdir, relative, env), f"config/{relative} ({env})")


def load_settings(*, environment: str | None = None, config_dir: Path | None = None) -> AppSettings:
    """Load and validate :class:`AppSettings` for the chosen environment."""
    cdir = config_dir or find_config_dir()
    env = resolve_environment(cdir, environment)
    data = _merged_layers(cdir, "app.yaml", env)
    if "environment" in data:
        raise ConfigError("config/app.yaml: 'environment' is derived, do not set it in YAML")
    data["environment"] = env
    return _validate(AppSettings, data, f"config/app.yaml ({env})")


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


class SecretStore:
    """Resolve secrets by environment variable name.

    Values are returned as :class:`pydantic.SecretStr` so they are not printed by
    accident. Missing secrets raise :class:`MissingSecretError`, which names the
    variables but never reveals values.
    """

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {k: v for k, v in values.items() if v}

    @classmethod
    def from_environment(cls, config_dir: Path | None = None) -> SecretStore:
        """Combine the repository ``.env`` file with the process environment (process wins)."""
        cdir = config_dir or find_config_dir()
        dotenv_file = cdir.parent / ".env"
        values: dict[str, str] = {}
        if dotenv_file.is_file():
            values.update({k: v for k, v in dotenv_values(dotenv_file).items() if v is not None})
        values.update(os.environ)
        return cls(values)

    def has(self, name: str) -> bool:
        """Return whether a non-empty value exists for ``name``."""
        return name in self._values

    def get(self, name: str) -> SecretStr | None:
        """Return the secret for ``name``, or ``None`` when it is not set."""
        value = self._values.get(name)
        return SecretStr(value) if value is not None else None

    def require(self, name: str) -> SecretStr:
        """Return the secret for ``name`` or raise :class:`MissingSecretError`."""
        return self.require_all([name])[name]

    def require_all(self, names: Iterable[str]) -> dict[str, SecretStr]:
        """Return all requested secrets, raising one error that lists every missing name."""
        wanted = list(dict.fromkeys(names))
        missing = [n for n in wanted if n not in self._values]
        if missing:
            raise MissingSecretError(missing)
        return {n: SecretStr(self._values[n]) for n in wanted}
