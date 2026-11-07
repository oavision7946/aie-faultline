"""Tests for the repository gates and the component template."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import new_component
import repo_checks

REPO_ROOT = Path(__file__).resolve().parents[2]

ROOT_PYPROJECT = """[project]
name = "x"
version = "0"

[tool.mypy]
mypy_path = "packages/core/src:packages/llm/src:apps/cli/src"
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal workspace with three template-generated components."""
    (tmp_path / "pyproject.toml").write_text(ROOT_PYPROJECT)
    for group, name in (("packages", "core"), ("packages", "llm"), ("apps", "cli")):
        files = new_component.render(name, f"faultline_{name}", f"The {name} component.")
        new_component.write_missing(tmp_path / group / name, files)
    return tmp_path


def test_template_component_passes_all_checks(repo: Path) -> None:
    assert repo_checks.check_components(repo) == []
    assert repo_checks.check_manifests(repo) == []
    assert repo_checks.check_imports(repo) == []


ARTIFACTS = [
    "src/faultline_llm/__init__.py",
    "src/faultline_llm/py.typed",
    "tests/test_llm_smoke.py",
    "README.md",
    "docs/index.md",
    "mkdocs.yml",
]


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_removing_any_artifact_fails(repo: Path, artifact: str) -> None:
    (repo / "packages" / "llm" / artifact).unlink()
    problems = repo_checks.check_components(repo)
    assert problems and all(p.startswith("packages/llm") for p in problems)


@pytest.mark.parametrize("section", repo_checks.README_SECTIONS)
def test_readme_sections_required(repo: Path, section: str) -> None:
    readme = repo / "packages" / "llm" / "README.md"
    readme.write_text(readme.read_text().replace(section, "## Other"))
    assert any(section in p for p in repo_checks.check_components(repo))


def test_docstring_and_static_analysis_required(repo: Path) -> None:
    (repo / "packages" / "llm" / "src" / "faultline_llm" / "__init__.py").write_text("X = 1\n")
    (repo / "pyproject.toml").write_text(ROOT_PYPROJECT.replace(":packages/llm/src", ""))
    problems = repo_checks.check_components(repo)
    assert any("docstring" in p for p in problems)
    assert any("mypy_path" in p for p in problems)


def test_no_components(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(ROOT_PYPROJECT)
    assert repo_checks.check_components(tmp_path) == ["no components found"]


@pytest.mark.parametrize(
    "name",
    ["requirements.txt", "requirements-dev.in", "Pipfile", "poetry.lock", "environment.yml",
     "setup.py", "package.json", "yarn.lock"],
)  # fmt: skip
def test_foreign_manifest_files_rejected(repo: Path, name: str) -> None:
    (repo / "packages" / "core" / name).write_text("")
    assert repo_checks.check_manifests(repo) == [
        f"packages/core/{name}: package-manager file not allowed (use uv)"
    ]


def test_foreign_tool_table_rejected(repo: Path) -> None:
    pyproject = repo / "packages" / "core" / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + "\n[tool.poetry]\nname = 'x'\n")
    assert repo_checks.check_manifests(repo) == [
        "packages/core/pyproject.toml: [tool.poetry] not allowed (use uv)"
    ]


def test_manifests_in_skipped_dirs_ignored(repo: Path) -> None:
    (repo / ".venv").mkdir()
    (repo / ".venv" / "requirements.txt").write_text("")
    assert repo_checks.check_manifests(repo) == []


def test_upward_import_rejected(repo: Path) -> None:
    src = repo / "packages" / "core" / "src" / "faultline_core" / "bad.py"
    src.write_text("import faultline_llm\nfrom faultline_cli.main import main\n")
    problems = repo_checks.check_imports(repo)
    assert "packages/core/src/faultline_core/bad.py:1: core may not import llm" in problems
    assert "packages/core/src/faultline_core/bad.py:2: core may not import cli" in problems


def test_downward_import_allowed(repo: Path) -> None:
    src = repo / "apps" / "cli" / "src" / "faultline_cli" / "ok.py"
    src.write_text("import faultline_core\nfrom faultline_llm import config\nfrom . import ok\n")
    assert repo_checks.check_imports(repo) == []


def test_declared_dependency_checked(repo: Path) -> None:
    pyproject = repo / "packages" / "core" / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("dependencies = []",
                         'dependencies = ["aie-faultline-llm>=0", "pydantic"]'))  # fmt: skip
    assert repo_checks.check_imports(repo) == [
        "packages/core/pyproject.toml: may not depend on llm"
    ]


@pytest.mark.parametrize(
    "code",
    ["import os\nos.environ['X']\n", "import os\nos.getenv('X')\n",
     "from os import environ\n", "import dotenv\n", "from dotenv import load_dotenv\n"],
)  # fmt: skip
def test_environment_access_outside_core_rejected(repo: Path, code: str) -> None:
    (repo / "packages" / "llm" / "src" / "faultline_llm" / "env.py").write_text(code)
    problems = repo_checks.check_imports(repo)
    assert len(problems) == 1 and "only core reads environment" in problems[0]


def test_environment_access_in_core_allowed(repo: Path) -> None:
    (repo / "packages" / "core" / "src" / "faultline_core" / "env.py").write_text(
        "import os\nos.environ\n"
    )
    assert repo_checks.check_imports(repo) == []


def test_unknown_component_flagged(repo: Path) -> None:
    files = new_component.render("mystery", "faultline_mystery", "Unknown.")
    new_component.write_missing(repo / "packages" / "mystery", files)
    assert repo_checks.check_imports(repo) == ["packages/mystery: not in the dependency rules"]


def test_main_list_and_all(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo_checks.main(["list", "--json", "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out) == ["packages/core", "packages/llm", "apps/cli"]
    assert repo_checks.main(["list", "--root", str(repo)]) == 0
    capsys.readouterr()
    assert repo_checks.main(["all", "--root", str(repo)]) == 0
    (repo / "packages" / "llm" / "mkdocs.yml").unlink()
    assert repo_checks.main(["components", "--root", str(repo)]) == 1
    assert "FAIL components" in capsys.readouterr().out


def test_real_repository_passes() -> None:
    assert repo_checks.main(["all", "--root", str(REPO_ROOT)]) == 0


# -- component template --------------------------------------------------------


def test_template_never_overwrites(repo: Path) -> None:
    readme = repo / "packages" / "core" / "README.md"
    readme.write_text("custom\n## Interface\n## Configuration\n## Tests\n")
    files = new_component.render("core", "faultline_core", "Changed.")
    assert new_component.write_missing(repo / "packages" / "core", files) == []
    assert readme.read_text().startswith("custom")


def test_template_api_component_mentions_api_suite() -> None:
    files = new_component.render("api", "faultline_api", "API.", api=True)
    assert "API test suite" in files["README.md"]
    assert "uv run pytest apps/api/tests" in files["README.md"]


def test_new_component_cli(repo: Path) -> None:
    assert (
        new_component.main(["packages", "Extra", "--description", "Extra.", "--root", str(repo)])
        == 0
    )
    assert (repo / "packages" / "extra" / "src" / "faultline_extra" / "__init__.py").is_file()
    with pytest.raises(SystemExit):
        new_component.main(["--root", str(repo)])


def test_fill_all_adds_missing_files_and_drops_gitkeep(repo: Path) -> None:
    comp = repo / "packages" / "core"
    (comp / "mkdocs.yml").unlink()
    (comp / "tests" / "test_core_smoke.py").unlink()
    (comp / "tests" / ".gitkeep").write_text("")
    assert new_component.main(["--fill-all", "--root", str(repo)]) == 0
    assert (comp / "mkdocs.yml").is_file()
    assert not (comp / "tests" / ".gitkeep").exists()
    assert "The core component." in (comp / "docs" / "index.md").read_text()


def test_fill_all_without_docstring(repo: Path) -> None:
    comp = repo / "packages" / "core"
    (comp / "src" / "faultline_core" / "__init__.py").write_text("")
    shutil.rmtree(comp / "docs")
    assert new_component.main(["--fill-all", "--root", str(repo)]) == 0
    assert "To be described." in (comp / "docs" / "index.md").read_text()
