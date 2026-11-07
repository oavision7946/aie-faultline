"""Smoke test: the package imports and documents itself."""

import faultline_cli


def test_package_imports_with_docstring() -> None:
    assert faultline_cli.__doc__
