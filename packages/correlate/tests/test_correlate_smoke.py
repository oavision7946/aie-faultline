"""Smoke test: the package imports and documents itself."""

import faultline_correlate


def test_package_imports_with_docstring() -> None:
    assert faultline_correlate.__doc__
