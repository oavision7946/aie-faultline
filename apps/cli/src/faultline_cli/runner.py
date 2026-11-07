"""Subprocess execution behind a small interface so commands can be tested with fakes."""

from __future__ import annotations

# Commands are fixed argument lists, never shell strings.
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

__all__ = ["Completed", "Runner", "SubprocessRunner"]


@dataclass(frozen=True)
class Completed:
    """Outcome of one command."""

    returncode: int
    stdout: str = ""


class Runner(Protocol):
    """Runs a command with an explicit environment."""

    def run(
        self, args: Sequence[str], env: Mapping[str, str], *, capture: bool = False
    ) -> Completed:
        """Run ``args``; capture standard output when ``capture`` is true."""
        ...


class SubprocessRunner:
    """Runs commands with :mod:`subprocess`, without a shell."""

    def run(
        self, args: Sequence[str], env: Mapping[str, str], *, capture: bool = False
    ) -> Completed:
        """Run ``args`` and return its exit code (and output when captured)."""
        try:
            # Argument list without a shell.
            proc = subprocess.run(  # nosec B603
                list(args),
                env=dict(env),
                check=False,
                text=True,
                stdout=subprocess.PIPE if capture else None,
            )
        except FileNotFoundError:
            return Completed(127, "")
        return Completed(proc.returncode, proc.stdout or "")
