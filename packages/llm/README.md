# aie-faultline-llm

Provider-agnostic LLM client interfaces and adapters.

**Status:** provider and model registry schema and offline checks implemented; client
adapters to come.

## Interface

| Name | Purpose |
|:--|:--|
| `faultline_llm.config.load_llm_config()` | Load and validate `config/llm/providers.yaml` |
| `LLMConfig` | Registry: `providers`, `models`, routing `profiles`; lookups `provider()`, `model()`, `resolve(profile, role)`, `enabled_providers(env)` |
| `ProviderEntry`, `ModelEntry`, `Pricing`, `Capabilities`, `DefaultParams`, `ModelLimits`, `LocalServing` | Typed registry entries |
| `faultline_llm.check.check_llm_config(config, env, has_secret)` | Offline check: key variables present, role capabilities consistent |

Provider types: `anthropic`, `openai`, `local_openai_compatible`. Roles: `triage`,
`investigator`, `reference`, `judge`.

## Configuration

| Source | Meaning |
|:--|:--|
| `config/llm/providers.yaml` | Providers, models, pricing and routing profiles |
| `config/llm/providers.<env>.yaml`, `config/local/llm/providers.yaml` | Optional overlays |
| Variables named by `api_key_env` | Provider keys, read only through `faultline_core` |

## Tests

```bash
uv run pytest packages/llm/tests
make test-component C=packages/llm
```
