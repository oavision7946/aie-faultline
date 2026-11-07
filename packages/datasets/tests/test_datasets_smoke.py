"""Smoke test: the package imports and documents itself."""

import faultline_datasets


def test_package_imports_with_docstring() -> None:
    assert faultline_datasets.__doc__
