"""Smoke test: the package imports and documents itself."""

import faultline_evals


def test_package_imports_with_docstring() -> None:
    assert faultline_evals.__doc__
