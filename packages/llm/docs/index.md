# aie-faultline-llm

Provider-agnostic LLM client interfaces and adapters.

## Provider registry

Providers and models are declared in `config/llm/providers.yaml`; nothing is hard-coded.

- **Provider**: name, type (`anthropic`, `openai`, `local_openai_compatible`), base URL, the
  name of the environment variable holding its key, and the environments it is enabled in.
- **Model**: registry id used across the code base, the provider's model name, roles,
  context window, capability flags, default parameters, pricing with an effective date,
  client-side limits and, for local models, quantization and serving stack.
- **Profiles**: named mappings from roles to model ids, so experiments refer to a profile
  instead of a model.

Adding a model is a YAML change. `faultline llm check` validates the providers enabled in
the selected environment without contacting them.

See the [API reference](reference.md).
