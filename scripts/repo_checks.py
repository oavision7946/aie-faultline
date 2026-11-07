"""Repository gates run by ``make check`` and CI.

Subcommands:

* ``components`` - every component has its required artifacts (tests, docs,
  typed package, README sections, docs config) and is covered by static analysis.
* ``manifests`` - no package-manager files other than ``uv``'s are present.
* ``imports`` - imports and declared dependencies follow the layering rules, and
  only ``core`` reads environment variables.
* ``list`` - print component paths (``--json`` for CI matrices).
* ``all`` - run every check.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ALLOWED_DEPENDENCIES",
    "Component",
    "check_components",
    "check_imports",
    "check_manifests",
    "discover_components",
    "main",
]

README_SECTIONS = ("## Interface", "## Configuration", "## Tests")
SKIP_DIRS = {".git", ".venv", ".internal", ".build", "node_modules", "data", "site", ".mypy_cache",
             ".ruff_cache", ".pytest_cache", "__pycache__", ".temp", ".branches"}  # fmt: skip

FORBIDDEN_MANIFESTS = re.compile(
    r"^(requirements.*\.(txt|in)|Pipfile(\.lock)?|poetry\.lock|pdm\.lock|setup\.py|setup\.cfg|"
    r"environment\.ya?ml|conda-lock\.ya?ml|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml)$"
)
FORBIDDEN_TOOL_TABLES = ("poetry", "pdm", "pipenv", "conda")

_L1 = {"datasets", "replay", "ingest", "llm", "knowledge"}
_L2 = {"detect", "correlate"}
_PACKAGES = {"core"} | _L1 | _L2 | {"tools", "agent", "evals"}

# component name -> components it may depend on
ALLOWED_DEPENDENCIES: dict[str, frozenset[str]] = {
    "core": frozenset(),
    **{name: frozenset({"core"}) for name in _L1},
    **{name: frozenset({"core"} | _L1) for name in _L2},
    "tools": frozenset({"core"} | _L1 | _L2),
    "agent": frozenset({"core"} | _L1 | _L2 | {"tools"}),
    "evals": frozenset(_PACKAGES - {"evals"}),
    # Applications sit on top. Only the CLI may use evals (it runs evaluations).
    "cli": frozenset(_PACKAGES),
    "api": frozenset(_PACKAGES - {"evals"}),
}

MODULE_PREFIX = "faultline_"
DIST_PREFIX = "aie-faultline-"
ENV_READERS = {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}


@dataclass(frozen=True)
class Component:
    """One workspace component (a package or an application)."""

    name: str
    path: Path
    module: str

    @property
    def is_api(self) -> bool:
        """True for the API application, whose tests form a separate suite."""
        return self.name == "api"


def _pyproject(path: Path) -> dict[str, object]:
    with (path / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def discover_components(root: Path) -> list[Component]:
    """Find every component under ``packages/`` and ``apps/`` that has a ``pyproject.toml``."""
    found: list[Component] = []
    for group in ("packages", "apps"):
        for path in sorted((root / group).glob("*/pyproject.toml")):
            comp_dir = path.parent
            data = _pyproject(comp_dir)
            tool = data.get("tool", {})
            backend = tool.get("uv", {}).get("build-backend", {}) if isinstance(tool, dict) else {}
            module = backend.get("module-name") if isinstance(backend, dict) else None
            name = comp_dir.name
            found.append(Component(name, comp_dir, str(module or f"{MODULE_PREFIX}{name}")))
    return found


def _mypy_paths(root: Path) -> set[str]:
    data = _pyproject(root)
    tool = data.get("tool", {})
    mypy = tool.get("mypy", {}) if isinstance(tool, dict) else {}
    raw = mypy.get("mypy_path", "") if isinstance(mypy, dict) else ""
    return {p.strip() for p in str(raw).split(":") if p.strip()}


def check_components(root: Path) -> list[str]:
    """Return one message per missing artifact."""
    problems: list[str] = []
    mypy_paths = _mypy_paths(root)
    components = discover_components(root)
    if not components:
        problems.append("no components found")
    for comp in components:
        rel = comp.path.relative_to(root)
        pkg = comp.path / "src" / comp.module

        def need(cond: bool, what: str, rel: Path = rel) -> None:
            if not cond:
                problems.append(f"{rel}: {what}")

        init = pkg / "__init__.py"
        need(init.is_file(), f"missing src/{comp.module}/__init__.py")
        if init.is_file():
            need(ast.get_docstring(ast.parse(init.read_text())) is not None,
                 "package __init__.py has no docstring")  # fmt: skip
        need((pkg / "py.typed").is_file(), f"missing src/{comp.module}/py.typed (typing marker)")
        tests = comp.path / "tests"
        need(any(tests.glob("test_*.py")), "no tests (tests/test_*.py)")
        readme = comp.path / "README.md"
        need(readme.is_file(), "missing README.md")
        if readme.is_file():
            text = readme.read_text()
            for section in README_SECTIONS:
                need(section in text, f"README.md lacks '{section}'")
        need((comp.path / "docs" / "index.md").is_file(), "missing docs/index.md")
        need((comp.path / "mkdocs.yml").is_file(), "missing mkdocs.yml (docs build)")
        need(f"{rel}/src" in mypy_paths, "src/ not in the root mypy_path (static analysis)")
    return problems


def _walk(root: Path) -> Iterator[Path]:
    for path in root.iterdir():
        if path.is_dir():
            if path.name not in SKIP_DIRS:
                yield from _walk(path)
        else:
            yield path


def check_manifests(root: Path) -> list[str]:
    """Return one message per non-``uv`` package-manager file or table."""
    problems: list[str] = []
    for path in _walk(root):
        rel = path.relative_to(root)
        if FORBIDDEN_MANIFESTS.match(path.name):
            problems.append(f"{rel}: package-manager file not allowed (use uv)")
        elif path.name == "pyproject.toml":
            tool = _pyproject(path.parent).get("tool", {})
            if isinstance(tool, dict):
                for table in FORBIDDEN_TOOL_TABLES:
                    if table in tool:
                        problems.append(f"{rel}: [tool.{table}] not allowed (use uv)")
    return problems


def _imported_components(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top.startswith(MODULE_PREFIX):
                yield node.lineno, top.removeprefix(MODULE_PREFIX)


def _env_access(tree: ast.AST) -> Iterator[int]:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in ENV_READERS
        ):
            yield node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(a.name in ENV_READERS for a in node.names):
                yield node.lineno
        elif isinstance(node, ast.Import | ast.ImportFrom):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            if any(m and m.split(".")[0] == "dotenv" for m in mods):
                yield node.lineno


def check_imports(root: Path) -> list[str]:
    """Return one message per layering or environment-access violation."""
    problems: list[str] = []
    for comp in discover_components(root):
        allowed = ALLOWED_DEPENDENCIES.get(comp.name)
        if allowed is None:
            problems.append(f"{comp.path.relative_to(root)}: not in the dependency rules")
            continue
        project = _pyproject(comp.path).get("project", {})
        deps = project.get("dependencies", []) if isinstance(project, dict) else []
        for dep in deps if isinstance(deps, list) else []:
            dist = re.split(r"[\s<>=!~;\[]", str(dep), maxsplit=1)[0]
            if dist.startswith(DIST_PREFIX):
                target = dist.removeprefix(DIST_PREFIX)
                if target not in allowed:
                    problems.append(
                        f"{comp.path.relative_to(root)}/pyproject.toml: may not depend on {target}"
                    )
        for sub in ("src", "tests"):
            for path in sorted((comp.path / sub).rglob("*.py")):
                rel = path.relative_to(root)
                tree = ast.parse(path.read_text(), filename=str(path))
                for lineno, target in _imported_components(tree):
                    if target != comp.name and target not in allowed:
                        problems.append(f"{rel}:{lineno}: {comp.name} may not import {target}")
                if comp.name != "core" and sub == "src":
                    for lineno in _env_access(tree):
                        problems.append(
                            f"{rel}:{lineno}: only core reads environment variables or .env"
                        )
    return problems


CHECKS = {"components": check_components, "manifests": check_manifests, "imports": check_imports}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested checks; return 1 if any problem is found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=[*CHECKS, "all", "list"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="with 'list': print a JSON array")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.command == "list":
        paths = [str(c.path.relative_to(root)) for c in discover_components(root)]
        print(json.dumps(paths) if args.json else "\n".join(paths))
        return 0

    names = list(CHECKS) if args.command == "all" else [args.command]
    failed = False
    for name in names:
        problems = CHECKS[name](root)
        status = "ok  " if not problems else "FAIL"
        print(f"{status} {name}")
        for problem in problems:
            print(f"       {problem}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
