"""Smoke test: the package imports and documents itself."""

import faultline_ingest


def test_package_imports_with_docstring() -> None:
    assert faultline_ingest.__doc__
