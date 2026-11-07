"""Smoke test: the package imports and documents itself."""

import faultline_detect


def test_package_imports_with_docstring() -> None:
    assert faultline_detect.__doc__
