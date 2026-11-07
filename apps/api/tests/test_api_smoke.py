"""Smoke test: the package imports and documents itself."""

import faultline_api


def test_package_imports_with_docstring() -> None:
    assert faultline_api.__doc__
