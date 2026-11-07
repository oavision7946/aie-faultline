"""Host checks: GPU availability and capacity (disk space and memory caps)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from faultline_cli.runner import Runner
from faultline_core.config import AppSettings

__all__ = [
    "CheckOutcome",
    "capacity_check",
    "gpu_check",
    "parse_memory_limit",
    "total_memory_bytes",
]

_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3}


@dataclass
class CheckOutcome:
    """Lines of findings plus an overall pass flag."""

    passed: bool = True
    lines: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        """Record a failing finding."""
        self.passed = False
        self.lines.append(f"FAIL {message}")

    def ok(self, message: str) -> None:
        """Record a passing finding."""
        self.lines.append(f"ok   {message}")


def parse_memory_limit(value: str) -> int:
    """Convert a Docker-style memory size such as ``24g`` to bytes."""
    value = value.strip().lower()
    if not value or value[-1] not in _UNITS or not value[:-1].isdigit():
        raise ValueError(f"invalid memory size: {value!r}")
    return int(value[:-1]) * _UNITS[value[-1]]


def total_memory_bytes() -> int:
    """Physical memory of this host."""
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def gpu_check(runner: Runner, env: Mapping[str, str]) -> CheckOutcome:
    """Verify that an NVIDIA GPU is visible and that Docker has the NVIDIA runtime."""
    outcome = CheckOutcome()
    query = ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]
    smi = runner.run(query, env, capture=True)
    gpus = [line.strip() for line in smi.stdout.splitlines() if line.strip()]
    if smi.returncode != 0 or not gpus:
        outcome.fail("no GPU reported by nvidia-smi")
    else:
        for gpu in gpus:
            outcome.ok(f"GPU: {gpu}")
    runtimes = runner.run(["docker", "info", "--format", "{{json .Runtimes}}"], env, capture=True)
    if runtimes.returncode != 0:
        outcome.fail("docker info failed")
    elif "nvidia" not in runtimes.stdout:
        outcome.fail("Docker has no 'nvidia' runtime")
    else:
        outcome.ok("Docker 'nvidia' runtime present")
    return outcome


def _existing_ancestor(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")


def capacity_check(
    settings: AppSettings,
    repo_root: Path,
    *,
    disk_free: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
    total_memory: Callable[[], int] = total_memory_bytes,
) -> CheckOutcome:
    """Check free disk space for the data directory and the ClickHouse memory cap."""
    outcome = CheckOutcome()
    data_dir = settings.paths.data_dir
    if not data_dir.is_absolute():
        data_dir = repo_root / data_dir
    free_gb = disk_free(_existing_ancestor(data_dir)) / 1024**3
    need = settings.capacity.min_free_disk_gb
    msg = f"free disk for {data_dir}: {free_gb:.1f} GB (minimum {need:g} GB)"
    outcome.ok(msg) if free_gb >= need else outcome.fail(msg)

    cap = parse_memory_limit(settings.clickhouse.memory_limit)
    total = total_memory()
    allowed = settings.capacity.max_clickhouse_memory_fraction * total
    msg = (
        f"ClickHouse memory cap {cap / 1024**3:.1f} GB of {total / 1024**3:.1f} GB "
        f"(maximum {settings.capacity.max_clickhouse_memory_fraction:.0%})"
    )
    outcome.ok(msg) if cap <= allowed else outcome.fail(msg)
    return outcome
