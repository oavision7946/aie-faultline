"""Smoke test: the package imports and documents itself."""

import faultline_core


def test_package_imports_with_docstring() -> None:
    assert faultline_core.__doc__
