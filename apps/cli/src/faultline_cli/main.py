"""Entry point for the ``faultline`` command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from faultline_cli.host_checks import capacity_check, gpu_check
from faultline_cli.runner import Runner, SubprocessRunner
from faultline_cli.stack import SERVICES, Service, Stack, StackError
from faultline_core.config import (
    ENVIRONMENTS,
    ConfigError,
    find_config_dir,
    load_settings,
    process_environment,
    resolve_environment,
    write_selected_environment,
)
from faultline_core.config import SecretStore as _SecretStore
from faultline_llm.check import check_llm_config
from faultline_llm.config import load_llm_config

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="faultline", description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, help="override the selected environment")
    sub = parser.add_subparsers(dest="command", required=True)

    env = sub.add_parser("env", help="select or show the configuration environment")
    env_sub = env.add_subparsers(dest="env_command", required=True)
    use = env_sub.add_parser("use", help="select the environment for this working copy")
    use.add_argument("name", choices=ENVIRONMENTS)
    env_sub.add_parser("show", help="print the effective settings (no secrets)")

    config = sub.add_parser("config", help="configuration utilities")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("validate", help="validate every config file for every environment")

    llm = sub.add_parser("llm", help="LLM provider configuration")
    llm_sub = llm.add_subparsers(dest="llm_command", required=True)
    llm_sub.add_parser("check", help="check enabled providers: keys present, roles consistent")

    stack = sub.add_parser("stack", help="local services: ClickHouse and Postgres")
    stack_sub = stack.add_subparsers(dest="stack_command", required=True)
    for name, text in (
        ("up", "start services and wait until healthy"),
        ("down", "stop services, keeping data"),
        ("reset", "delete local data and start services again"),
    ):
        p = stack_sub.add_parser(name, help=text)
        p.add_argument("services", nargs="*", metavar="SERVICE", help="clickhouse, postgres")
    stack_sub.add_parser("status", help="show service status")
    stack_sub.add_parser("db-reset", help="recreate Postgres from migrations and seed")

    sub.add_parser("gpu-check", help="verify GPU and container GPU runtime")
    sub.add_parser("capacity-check", help="verify disk space and memory caps")
    return parser


def _services(names: Sequence[str]) -> list[Service]:
    unknown = sorted(set(names) - set(SERVICES))
    if unknown:
        raise StackError(f"unknown service(s): {', '.join(unknown)}")
    return [s for s in SERVICES if s in names] if names else list(SERVICES)


def _run(args: argparse.Namespace, runner: Runner) -> int:
    config_dir = find_config_dir()
    repo_root = config_dir.parent

    if args.command == "env" and args.env_command == "use":
        env = write_selected_environment(config_dir, args.name)
        print(f"environment: {env}")
        return 0

    if args.command == "config":
        for env_name in ENVIRONMENTS:
            load_settings(environment=env_name, config_dir=config_dir)
            load_llm_config(environment=env_name, config_dir=config_dir)
            print(f"ok   {env_name}")
        return 0

    settings = load_settings(environment=args.env, config_dir=config_dir)

    if args.command == "env":
        print(settings.model_dump_json(indent=2))
        return 0

    if args.command == "llm":
        environment = resolve_environment(config_dir, args.env)
        llm_config = load_llm_config(environment=environment, config_dir=config_dir)
        secrets = _SecretStore.from_environment(config_dir)
        reports = check_llm_config(llm_config, environment, secrets.has)
        for report in reports:
            print(f"{'ok  ' if report.ok else 'FAIL'} {report.provider}")
            for line in report.problems:
                print(f"       problem: {line}")
            for line in report.notes:
                print(f"       note: {line}")
        if not reports:
            print(f"no providers enabled in {environment}")
        return 0 if all(r.ok for r in reports) else 1

    if args.command == "gpu-check":
        outcome = gpu_check(runner, process_environment())
    elif args.command == "capacity-check":
        outcome = capacity_check(settings, repo_root)
    else:
        stack = Stack(
            settings, repo_root, _SecretStore.from_environment(config_dir), runner,
            process_environment(),
        )  # fmt: skip
        command = args.stack_command
        if command == "status":
            return stack.status()
        if command == "db-reset":
            stack.db_reset()
        elif command == "up":
            stack.up(_services(args.services))
        elif command == "down":
            stack.down(_services(args.services))
        else:
            stack.reset(_services(args.services))
        print(f"stack {command}: done")
        return 0

    for line in outcome.lines:
        print(line)
    return 0 if outcome.passed else 1


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    """Run the CLI and return an exit code."""
    args = build_parser().parse_args(argv)
    try:
        return _run(args, runner or SubprocessRunner())
    except (ConfigError, StackError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
