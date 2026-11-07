"""Unit tests for the CLI, using a fake command runner (no Docker, no network)."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from faultline_cli import main as cli
from faultline_cli.host_checks import capacity_check, gpu_check, parse_memory_limit
from faultline_cli.runner import Completed, SubprocessRunner
from faultline_cli.stack import (
    SUPABASE_EXCLUDED_CONTAINERS,
    Stack,
    StackError,
    compose_environment,
    supabase_environment,
)
from faultline_core.config import (
    CONFIG_DIR_ENV_VAR,
    ENVIRONMENT_ENV_VAR,
    AppSettings,
    MissingSecretError,
    SecretStore,
)

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"
SECRETS = {"CLICKHOUSE_WRITER_PASSWORD": "w-pass", "CLICKHOUSE_READONLY_PASSWORD": "r-pass"}


@dataclass
class FakeRunner:
    """Records commands and returns scripted results by first matching prefix."""

    results: dict[str, Completed] = field(default_factory=dict)
    calls: list[tuple[list[str], dict[str, str]]] = field(default_factory=list)

    def run(
        self, args: Sequence[str], env: Mapping[str, str], *, capture: bool = False
    ) -> Completed:
        self.calls.append((list(args), dict(env)))
        joined = " ".join(args)
        for prefix, result in self.results.items():
            if joined.startswith(prefix):
                return result
        return Completed(0, "")

    def commands(self) -> list[str]:
        return [" ".join(args) for args, _ in self.calls]


BRIDGE = "docker network inspect bridge"


def settings(**overrides: object) -> AppSettings:
    return AppSettings.model_validate({"environment": "dev", **overrides})


def make_stack(runner: FakeRunner, **overrides: object) -> Stack:
    return Stack(
        settings(**overrides), Path("/repo"), SecretStore(SECRETS), runner, {"PATH": "/bin"}
    )


# -- stack -----------------------------------------------------------------


def test_compose_environment_uses_settings_and_secrets() -> None:
    env = compose_environment(settings(clickhouse={"http_port": 18123}), SecretStore(SECRETS))
    assert env["CLICKHOUSE_HTTP_PORT"] == "18123"
    assert env["FAULTLINE_BIND_HOST"] == "127.0.0.1"
    assert env["CLICKHOUSE_WRITER_PASSWORD"] == "w-pass"
    assert env["CLICKHOUSE_RO_MAX_EXECUTION_TIME"] == "30"


def test_compose_environment_fails_fast_without_secrets() -> None:
    with pytest.raises(MissingSecretError, match="CLICKHOUSE_READONLY_PASSWORD"):
        compose_environment(settings(), SecretStore({"CLICKHOUSE_WRITER_PASSWORD": "x"}))


def test_supabase_environment_ports() -> None:
    env = supabase_environment(settings(postgres={"port": 55432, "shadow_port": 55430}))
    assert env == {"SUPABASE_DB_PORT": "55432", "SUPABASE_SHADOW_PORT": "55430"}


def test_up_starts_clickhouse_and_postgres() -> None:
    runner = FakeRunner({BRIDGE: Completed(0, "127.0.0.1\n")})
    make_stack(runner).up()
    cmds = runner.commands()
    assert cmds[0] == "docker compose -f /repo/infra/compose/compose.yaml up -d --wait"
    assert "CREATE DATABASE IF NOT EXISTS faultline" in cmds[1]
    assert cmds[-1] == f"supabase start -x {SUPABASE_EXCLUDED_CONTAINERS} --workdir /repo"
    _, create_env = runner.calls[1]
    assert create_env["CLICKHOUSE_PASSWORD"] == "w-pass"
    assert "w-pass" not in cmds[1]  # never on the command line
    _, supa_env = runner.calls[-1]
    assert supa_env["SUPABASE_DB_PORT"] == "54322" and supa_env["PATH"] == "/bin"


def test_postgres_refused_on_wildcard_bind() -> None:
    runner = FakeRunner({BRIDGE: Completed(0, "0.0.0.0\n")})
    with pytest.raises(StackError, match="every network interface"):
        make_stack(runner).up(["postgres"])
    assert not any(c.startswith("supabase start") for c in runner.commands())


def test_postgres_wildcard_allowed_by_setting() -> None:
    runner = FakeRunner({BRIDGE: Completed(0, "")})  # empty means Docker's default, 0.0.0.0
    make_stack(runner, postgres={"allow_wildcard_bind": True}).up(["postgres"])
    assert runner.commands()[-1].startswith("supabase start")


def test_bind_inspection_failure() -> None:
    runner = FakeRunner({BRIDGE: Completed(1, "")})
    with pytest.raises(StackError, match="inspect"):
        make_stack(runner).up(["postgres"])


def test_failed_command_raises() -> None:
    runner = FakeRunner({"docker compose": Completed(1)})
    with pytest.raises(StackError, match="starting ClickHouse failed"):
        make_stack(runner).up(["clickhouse"])


def test_reset_deletes_volumes_then_starts() -> None:
    runner = FakeRunner({BRIDGE: Completed(0, "127.0.0.1")})
    make_stack(runner).reset()
    cmds = runner.commands()
    assert cmds[0].endswith("down -v")
    assert cmds[1] == "supabase stop --no-backup --workdir /repo"
    assert any(c.endswith("up -d --wait") for c in cmds[2:])


def test_down_keeps_data_and_db_reset_and_status() -> None:
    runner = FakeRunner()
    stack = make_stack(runner)
    stack.down()
    stack.db_reset()
    assert stack.status() == 0
    cmds = runner.commands()
    assert cmds[0].endswith("compose.yaml down")
    assert cmds[1] == "supabase stop --workdir /repo"
    assert cmds[2] == "supabase db reset --local --workdir /repo"
    assert cmds[-1] == "supabase status --workdir /repo"


# -- host checks -----------------------------------------------------------


def test_parse_memory_limit() -> None:
    assert parse_memory_limit("24g") == 24 * 1024**3
    assert parse_memory_limit("512m") == 512 * 1024**2
    for bad in ("", "12", "g", "1.5g", "4t"):
        with pytest.raises(ValueError):
            parse_memory_limit(bad)


def test_gpu_check_pass_and_fail() -> None:
    ok = FakeRunner({"nvidia-smi": Completed(0, "GPU X, 1.0\n"),
                     "docker info": Completed(0, '{"nvidia":{}}')})  # fmt: skip
    assert gpu_check(ok, {}).passed
    no_gpu = FakeRunner({"nvidia-smi": Completed(127, ""), "docker info": Completed(0, "{}")})
    outcome = gpu_check(no_gpu, {})
    assert not outcome.passed and len([x for x in outcome.lines if x.startswith("FAIL")]) == 2
    broken = FakeRunner({"nvidia-smi": Completed(0, "GPU\n"), "docker info": Completed(1, "")})
    assert not gpu_check(broken, {}).passed


def test_capacity_check(tmp_path: Path) -> None:
    gib = 1024**3
    s = settings(
        paths={"data_dir": str(tmp_path / "missing" / "data")},
        capacity={"min_free_disk_gb": 10, "max_clickhouse_memory_fraction": 0.5},
    )
    ok = capacity_check(s, tmp_path, disk_free=lambda p: 50 * gib, total_memory=lambda: 16 * gib)
    assert ok.passed
    low = capacity_check(s, tmp_path, disk_free=lambda p: 1 * gib, total_memory=lambda: 4 * gib)
    assert not low.passed and len(low.lines) == 2


def test_capacity_check_relative_data_dir(tmp_path: Path) -> None:
    seen: list[Path] = []

    def disk_free(path: Path) -> int:
        seen.append(path)
        return 10**15

    assert capacity_check(
        settings(), tmp_path, disk_free=disk_free, total_memory=lambda: 10**12
    ).passed
    assert seen == [tmp_path]  # data/ does not exist yet, so its parent is measured


def test_subprocess_runner() -> None:
    runner = SubprocessRunner()
    assert runner.run(["definitely-not-a-command-xyz"], {}).returncode == 127
    true_cmd = shutil.which("true")
    assert true_cmd is not None
    assert runner.run([true_cmd], {}).returncode == 0
    echo = shutil.which("echo")
    assert echo is not None
    assert runner.run([echo, "hi"], {}, capture=True).stdout == "hi\n"


# -- command line ------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(REPO_CONFIG, tmp_path / "config", ignore=shutil.ignore_patterns("local"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENVIRONMENT_ENV_VAR, raising=False)
    monkeypatch.delenv(CONFIG_DIR_ENV_VAR, raising=False)
    return tmp_path


def test_cli_env_use_and_show(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["env", "use", "lab"]) == 0
    assert (repo / ".faultline" / "env").read_text().strip() == "lab"
    assert cli.main(["env", "show"]) == 0
    assert '"environment": "lab"' in capsys.readouterr().out


def test_cli_config_validate(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["config", "validate"]) == 0
    assert capsys.readouterr().out.count("ok") == 3


def test_cli_llm_check(repo: Path, monkeypatch: pytest.MonkeyPatch,
                       capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["--env", "dev", "llm", "check"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert cli.main(["--env", "dev", "llm", "check"]) == 0
    assert cli.main(["--env", "ci", "llm", "check"]) == 0
    assert "no providers enabled in ci" in capsys.readouterr().out


def test_cli_stack_commands(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    runner = FakeRunner({BRIDGE: Completed(0, "127.0.0.1")})
    for argv in (["stack", "up", "clickhouse"], ["stack", "down"], ["stack", "reset", "postgres"],
                 ["stack", "db-reset"], ["stack", "status"]):  # fmt: skip
        assert cli.main(argv, runner) == 0, argv
    assert cli.main(["stack", "up", "bogus"], runner) == 2


def test_cli_reports_config_errors(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "config" / "app.yaml").write_text("nonsense_key: 1\n")
    assert cli.main(["env", "show"]) == 2
    assert "nonsense_key" in capsys.readouterr().err


def test_cli_host_checks(repo: Path) -> None:
    runner = FakeRunner(
        {"nvidia-smi": Completed(0, "GPU\n"), "docker info": Completed(0, "nvidia")}
    )
    assert cli.main(["gpu-check"], runner) == 0
    assert cli.main(["gpu-check"], FakeRunner()) == 1
    assert cli.main(["capacity-check"], runner) in (0, 1)
