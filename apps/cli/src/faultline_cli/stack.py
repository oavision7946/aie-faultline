"""Lifecycle of the local service stack: ClickHouse (Docker Compose) and Postgres (Supabase CLI).

All ports, limits and image versions come from :class:`faultline_core.config.AppSettings`;
secrets come from :class:`faultline_core.config.SecretStore`. Nothing here reads
files or environment variables directly.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from faultline_cli.runner import Runner
from faultline_core.config import AppSettings, SecretStore

__all__ = [
    "SERVICES",
    "SUPABASE_EXCLUDED_CONTAINERS",
    "Service",
    "Stack",
    "StackError",
    "compose_environment",
    "supabase_environment",
]

Service = Literal["clickhouse", "postgres"]
SERVICES: tuple[Service, ...] = ("clickhouse", "postgres")

# Everything except the database itself is excluded from the Supabase local stack.
SUPABASE_EXCLUDED_CONTAINERS = (
    "gotrue,realtime,storage-api,imgproxy,kong,mailpit,postgrest,"
    "postgres-meta,studio,edge-runtime,logflare,vector,supavisor"
)
CLICKHOUSE_CONTAINER = "faultline-clickhouse"
COMPOSE_FILE = Path("infra/compose/compose.yaml")


class StackError(RuntimeError):
    """Raised when a stack operation fails."""


def compose_environment(settings: AppSettings, secrets: SecretStore) -> dict[str, str]:
    """Variables the ClickHouse compose file needs (secrets included)."""
    ch = settings.clickhouse
    found = secrets.require_all(settings.stack_secret_names())
    limits = ch.readonly_limits
    return {
        "CLICKHOUSE_IMAGE": ch.image,
        "FAULTLINE_BIND_HOST": settings.bind_host,
        "CLICKHOUSE_HTTP_PORT": str(ch.http_port),
        "CLICKHOUSE_NATIVE_PORT": str(ch.native_port),
        "CLICKHOUSE_MEMORY_LIMIT": ch.memory_limit,
        "CLICKHOUSE_RO_MAX_EXECUTION_TIME": str(limits.max_execution_time_s),
        "CLICKHOUSE_RO_MAX_RESULT_ROWS": str(limits.max_result_rows),
        "CLICKHOUSE_RO_MAX_ROWS_TO_READ": str(limits.max_rows_to_read),
        "CLICKHOUSE_RO_MAX_MEMORY_USAGE": str(limits.max_memory_usage_bytes),
        "CLICKHOUSE_WRITER_PASSWORD": found[ch.writer_password_env].get_secret_value(),
        "CLICKHOUSE_READONLY_PASSWORD": found[ch.readonly_password_env].get_secret_value(),
    }


def supabase_environment(settings: AppSettings) -> dict[str, str]:
    """Variables referenced by ``supabase/config.toml``."""
    return {
        "SUPABASE_DB_PORT": str(settings.postgres.port),
        "SUPABASE_SHADOW_PORT": str(settings.postgres.shadow_port),
    }


def _is_wildcard(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


@dataclass
class Stack:
    """Start, stop and reset the local services."""

    settings: AppSettings
    repo_root: Path
    secrets: SecretStore
    runner: Runner
    base_env: Mapping[str, str]

    # -- helpers ---------------------------------------------------------

    def _env(self, extra: Mapping[str, str]) -> dict[str, str]:
        return {**self.base_env, **extra}

    def _compose(self, *args: str) -> list[str]:
        return ["docker", "compose", "-f", str(self.repo_root / COMPOSE_FILE), *args]

    def _supabase(self, *args: str) -> list[str]:
        return ["supabase", *args, "--workdir", str(self.repo_root)]

    def _check(self, args: list[str], env: Mapping[str, str], what: str) -> None:
        result = self.runner.run(args, env)
        if result.returncode != 0:
            raise StackError(f"{what} failed (exit {result.returncode})")

    # -- ClickHouse ------------------------------------------------------

    def _clickhouse_up(self) -> None:
        env = self._env(compose_environment(self.settings, self.secrets))
        self._check(self._compose("up", "-d", "--wait"), env, "starting ClickHouse")
        ch = self.settings.clickhouse
        password = self.secrets.require(ch.writer_password_env).get_secret_value()
        create = [
            "docker", "exec", "-e", "CLICKHOUSE_PASSWORD", CLICKHOUSE_CONTAINER,
            "clickhouse-client", "--user", ch.writer_user,
            "--query", f"CREATE DATABASE IF NOT EXISTS {ch.database}",
        ]  # fmt: skip
        self._check(create, self._env({"CLICKHOUSE_PASSWORD": password}), "creating database")

    def _clickhouse_down(self, volumes: bool) -> None:
        env = self._env(compose_environment(self.settings, self.secrets))
        args = self._compose("down", *(["-v"] if volumes else []))
        self._check(args, env, "stopping ClickHouse")

    # -- Postgres (Supabase) ---------------------------------------------

    def docker_default_bind_host(self) -> str:
        """Return the address Docker publishes ports on when none is given."""
        args = [
            "docker", "network", "inspect", "bridge", "--format",
            '{{index .Options "com.docker.network.bridge.host_binding_ipv4"}}',
        ]  # fmt: skip
        result = self.runner.run(args, self._env({}), capture=True)
        if result.returncode != 0:
            raise StackError("could not inspect Docker's default network")
        # An empty value means Docker's documented default, the wildcard address.
        return result.stdout.strip() or "0.0.0.0"  # nosec B104

    def _guard_bind(self) -> None:
        host = self.docker_default_bind_host()
        if _is_wildcard(host) and not self.settings.postgres.allow_wildcard_bind:
            raise StackError(
                f"Docker publishes ports on {host} by default, which would expose Postgres "
                "on every network interface. Set Docker's default bind address to a "
                "loopback or private address, or set postgres.allow_wildcard_bind: true "
                "in config/local/app.yaml to accept the exposure."
            )

    def _postgres_up(self) -> None:
        self._guard_bind()
        args = self._supabase("start", "-x", SUPABASE_EXCLUDED_CONTAINERS)
        self._check(args, self._env(supabase_environment(self.settings)), "starting Postgres")

    def _postgres_down(self, volumes: bool) -> None:
        args = self._supabase("stop", *(["--no-backup"] if volumes else []))
        self._check(args, self._env(supabase_environment(self.settings)), "stopping Postgres")

    # -- public operations -----------------------------------------------

    def up(self, services: Iterable[Service] = SERVICES) -> None:
        """Start the selected services and wait until they are healthy."""
        for service in services:
            self._clickhouse_up() if service == "clickhouse" else self._postgres_up()

    def down(self, services: Iterable[Service] = SERVICES, *, volumes: bool = False) -> None:
        """Stop the selected services; ``volumes`` also deletes their data."""
        for service in services:
            if service == "clickhouse":
                self._clickhouse_down(volumes)
            else:
                self._postgres_down(volumes)

    def reset(self, services: Iterable[Service] = SERVICES) -> None:
        """Delete all local data for the selected services and start them again."""
        selected = list(services)
        self.down(selected, volumes=True)
        self.up(selected)

    def db_reset(self) -> None:
        """Recreate the Postgres database from migrations and the seed file."""
        args = self._supabase("db", "reset", "--local")
        self._check(args, self._env(supabase_environment(self.settings)), "database reset")

    def status(self) -> int:
        """Print service status; return non-zero if any status command failed."""
        rc_compose = self.runner.run(
            ["docker", "ps", "--filter", f"name={CLICKHOUSE_CONTAINER}"], self._env({})
        ).returncode
        rc_supabase = self.runner.run(
            self._supabase("status"), self._env(supabase_environment(self.settings))
        ).returncode
        return max(rc_compose, rc_supabase)
