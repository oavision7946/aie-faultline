"""Create a workspace component from the shared template, or fill in missing template files.

Usage::

    uv run python scripts/new_component.py packages <name> --description "One line."
    uv run python scripts/new_component.py apps <name> --description "One line."
    uv run python scripts/new_component.py --fill-all     # add missing files to every component

Existing files are never overwritten. After creating a component, add it to the
root ``pyproject.toml`` (workspace sources, dev group and ``mypy_path``) and to
the dependency rules in ``scripts/repo_checks.py``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_checks import discover_components

__all__ = ["main", "render", "write_missing"]

ROOT = Path(__file__).resolve().parents[1]
UV_BUILD = "uv_build>=0.11.20,<0.12.0"


def render(name: str, module: str, description: str, *, api: bool = False) -> dict[str, str]:
    """Return the template files for a component, keyed by relative path."""
    dist = f"aie-faultline-{name}"
    suite = "the API test suite" if api else "the component unit tests"
    run_tests = f"uv run pytest {'apps' if api else 'packages'}/{name}/tests"
    return {
        "pyproject.toml": f'''[project]
name = "{dist}"
version = "0.0.0"
description = "{description}"
readme = "README.md"
requires-python = ">=3.13"
dependencies = []

[build-system]
requires = ["{UV_BUILD}"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "{module}"
''',
        "README.md": f"""# {dist}

{description}

**Status:** scaffold only.

## Interface

No public interface yet. The package `{module}` is importable.

## Configuration

Reads no configuration and no environment variables.

## Tests

Tests live in `tests/` and belong to {suite}:

```bash
{run_tests}
```
""",
        "docs/index.md": f"# {dist}\n\n{description}\n\nSee the [API reference](reference.md).\n",
        "docs/reference.md": f"# API reference\n\n::: {module}\n",
        "mkdocs.yml": f"""site_name: {dist}
docs_dir: docs
strict: true
nav:
  - Overview: index.md
  - API reference: reference.md
plugins:
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
""",
        f"src/{module}/__init__.py": f'"""{description}"""\n',
        f"src/{module}/py.typed": "",
        f"tests/test_{name}_smoke.py": f'''"""Smoke test: the package imports."""

import {module}


def test_package_imports_with_docstring() -> None:
    assert {module}.__doc__
''',
    }


def write_missing(component_dir: Path, files: dict[str, str]) -> list[Path]:
    """Write template files that do not exist yet; return the paths written."""
    written: list[Path] = []
    for rel, content in files.items():
        path = component_dir / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    keep = component_dir / "tests" / ".gitkeep"
    if keep.exists() and any((component_dir / "tests").glob("test_*.py")):
        keep.unlink()
    return written


def _description(component_dir: Path) -> str:
    init = next((component_dir / "src").glob("*/__init__.py"), None)
    if init is not None:
        first = init.read_text(encoding="utf-8").strip().strip('"').splitlines()
        if first and first[0].strip():
            return first[0].strip()
    return "To be described."


def main(argv: Sequence[str] | None = None) -> int:
    """Create a component, or fill every existing component with missing template files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("group", nargs="?", choices=["packages", "apps"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--description", default="To be described.")
    parser.add_argument("--fill-all", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.fill_all:
        for comp in discover_components(args.root):
            files = render(comp.name, comp.module, _description(comp.path), api=comp.is_api)
            for path in write_missing(comp.path, files):
                print(f"created {path.relative_to(args.root)}")
        return 0
    if not (args.group and args.name):
        parser.error("give GROUP and NAME, or --fill-all")
    name = args.name.lower()
    target = args.root / args.group / name
    files = render(name, f"faultline_{name}", args.description, api=name == "api")
    for path in write_missing(target, files):
        print(f"created {path.relative_to(args.root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
