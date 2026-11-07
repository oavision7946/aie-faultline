"""Smoke test: the package imports and documents itself."""

import faultline_knowledge


def test_package_imports_with_docstring() -> None:
    assert faultline_knowledge.__doc__
