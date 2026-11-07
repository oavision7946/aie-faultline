"""Smoke test: the package imports and documents itself."""

import faultline_replay


def test_package_imports_with_docstring() -> None:
    assert faultline_replay.__doc__
