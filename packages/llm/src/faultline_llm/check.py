"""Offline validation of the LLM provider configuration (the ``llm check`` command).

The checks run without network access: every provider enabled in the selected
environment must have its API key variable set (when it declares one), and every
model's capabilities must be consistent with the roles it is assigned.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from faultline_core.config import Environment
from faultline_llm.config import LLMConfig, ModelEntry, Role

__all__ = ["ProviderReport", "check_llm_config", "role_problems"]

_ROLE_REQUIREMENTS: dict[Role, tuple[str, ...]] = {
    "investigator": ("tool_calling", "structured_output"),
    "judge": ("structured_output",),
    "triage": ("structured_output",),
    "reference": (),
}


@dataclass
class ProviderReport:
    """Result of checking one provider."""

    provider: str
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no problems were found."""
        return not self.problems


def role_problems(model: ModelEntry) -> list[str]:
    """Return capability problems for the roles assigned to ``model``."""
    problems: list[str] = []
    caps = model.capabilities.model_dump()
    for role in model.roles:
        for capability in _ROLE_REQUIREMENTS[role]:
            if not caps[capability]:
                problems.append(f"model {model.id!r}: role {role!r} needs {capability}")
    return problems


def check_llm_config(
    config: LLMConfig,
    environment: Environment,
    has_secret: Callable[[str], bool],
) -> list[ProviderReport]:
    """Check every provider enabled in ``environment``.

    ``has_secret`` reports whether an environment variable is set; it is
    injected so the check never handles secret values itself.
    """
    reports: list[ProviderReport] = []
    for provider in config.enabled_providers(environment):
        report = ProviderReport(provider.name)
        if provider.api_key_env and not has_secret(provider.api_key_env):
            if provider.type == "local_openai_compatible":
                report.notes.append(f"{provider.api_key_env} not set (optional for local servers)")
            else:
                report.problems.append(f"{provider.api_key_env} is not set")
        models = config.models_for(provider.name)
        if not models:
            report.notes.append("no models declared")
        for model in models:
            report.problems.extend(role_problems(model))
        reports.append(report)
    return reports
