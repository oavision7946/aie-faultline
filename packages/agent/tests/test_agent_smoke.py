"""Smoke test: the package imports and documents itself."""

import faultline_agent


def test_package_imports_with_docstring() -> None:
    assert faultline_agent.__doc__
