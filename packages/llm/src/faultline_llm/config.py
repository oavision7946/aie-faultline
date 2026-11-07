"""Schema for the LLM provider and model registry (``config/llm/providers.yaml``).

Providers and models are never hard-coded: they are declared in YAML, loaded by
the configuration loader in ``faultline_core``, and validated by these models.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, model_validator

from faultline_core.config import Environment, StrictModel, load_config

__all__ = [
    "PROVIDERS_CONFIG_PATH",
    "Capabilities",
    "DefaultParams",
    "LLMConfig",
    "LocalServing",
    "ModelEntry",
    "ModelLimits",
    "Pricing",
    "ProviderEntry",
    "ProviderType",
    "Role",
    "load_llm_config",
]

PROVIDERS_CONFIG_PATH = "llm/providers.yaml"

ProviderType = Literal["anthropic", "openai", "local_openai_compatible"]
Role = Literal["triage", "investigator", "reference", "judge"]

_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
_ENV_VAR_PATTERN = r"^[A-Z][A-Z0-9_]*$"


class Capabilities(StrictModel):
    """What a model supports."""

    tool_calling: bool
    structured_output: bool


class DefaultParams(StrictModel):
    """Default request parameters for a model."""

    max_output_tokens: int = Field(gt=0)
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    temperature: float | None = Field(default=None, ge=0, le=2)


class Pricing(StrictModel):
    """Price per million tokens, with the date the figures took effect."""

    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)
    currency: Literal["USD"] = "USD"
    effective_date: date


class ModelLimits(StrictModel):
    """Client-side rate, concurrency and spend limits."""

    requests_per_minute: int | None = Field(default=None, gt=0)
    max_concurrency: int = Field(default=4, gt=0)
    max_spend_usd_per_run: Decimal | None = Field(default=None, gt=0)


class LocalServing(StrictModel):
    """How a self-hosted model is served."""

    quantization: str
    serving_stack: str


class ProviderEntry(StrictModel):
    """One provider endpoint."""

    name: str = Field(pattern=_ID_PATTERN)
    type: ProviderType
    base_url: AnyHttpUrl
    api_key_env: str | None = Field(default=None, pattern=_ENV_VAR_PATTERN)
    enabled_in: list[Environment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hosted_needs_key(self) -> Self:
        if self.type != "local_openai_compatible" and self.api_key_env is None:
            raise ValueError(f"provider {self.name!r}: hosted providers need api_key_env")
        return self


class ModelEntry(StrictModel):
    """One model in the registry. ``id`` is the name used everywhere else in the code base."""

    id: str = Field(pattern=_ID_PATTERN)
    provider: str
    model_name: str
    roles: list[Role] = Field(min_length=1)
    context_window: int = Field(gt=0)
    capabilities: Capabilities
    defaults: DefaultParams
    pricing: Pricing
    limits: ModelLimits = ModelLimits()
    local: LocalServing | None = None


class LLMConfig(StrictModel):
    """The complete provider and model registry."""

    providers: list[ProviderEntry]
    models: list[ModelEntry] = Field(default_factory=list)
    profiles: dict[str, dict[Role, str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        provider_names = [p.name for p in self.providers]
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("provider names must be unique")
        model_ids = [m.id for m in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("model ids must be unique")
        providers = {p.name: p for p in self.providers}
        for model in self.models:
            provider = providers.get(model.provider)
            if provider is None:
                raise ValueError(f"model {model.id!r}: unknown provider {model.provider!r}")
            is_local = provider.type == "local_openai_compatible"
            if is_local and model.local is None:
                raise ValueError(f"model {model.id!r}: local models need a 'local' block")
            if not is_local and model.local is not None:
                raise ValueError(f"model {model.id!r}: 'local' is only for local providers")
        known = set(model_ids)
        for profile, mapping in self.profiles.items():
            for role, model_id in mapping.items():
                if model_id not in known:
                    raise ValueError(f"profile {profile!r}: role {role!r} -> unknown {model_id!r}")
        return self

    def provider(self, name: str) -> ProviderEntry:
        """Return the provider called ``name``."""
        for p in self.providers:
            if p.name == name:
                return p
        raise KeyError(name)

    def model(self, model_id: str) -> ModelEntry:
        """Return the model with registry id ``model_id``."""
        for m in self.models:
            if m.id == model_id:
                return m
        raise KeyError(model_id)

    def enabled_providers(self, environment: Environment) -> list[ProviderEntry]:
        """Providers enabled in ``environment``."""
        return [p for p in self.providers if environment in p.enabled_in]

    def models_for(self, provider: str) -> list[ModelEntry]:
        """Models served by ``provider``."""
        return [m for m in self.models if m.provider == provider]

    def resolve(self, profile: str, role: Role) -> ModelEntry:
        """Return the model a routing profile assigns to ``role``."""
        try:
            return self.model(self.profiles[profile][role])
        except KeyError as exc:
            raise KeyError(f"profile {profile!r} has no model for role {role!r}") from exc


def load_llm_config(*, environment: str | None = None, config_dir: Path | None = None) -> LLMConfig:
    """Load ``config/llm/providers.yaml`` (with overlays) through the core loader."""
    return load_config(
        PROVIDERS_CONFIG_PATH, LLMConfig, environment=environment, config_dir=config_dir
    )
