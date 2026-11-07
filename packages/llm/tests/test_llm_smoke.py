"""Smoke test: the package imports and documents itself."""

import faultline_llm


def test_package_imports_with_docstring() -> None:
    assert faultline_llm.__doc__
