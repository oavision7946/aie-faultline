# aie-faultline-core

Domain models, identifiers and shared configuration support.

**Status:** configuration and secrets loading implemented; domain models to come.

## Interface

`faultline_core.config` is the only module in the code base that reads configuration
files or environment variables.

| Name | Purpose |
|:--|:--|
| `load_settings(environment=None, config_dir=None)` | Load `config/app.yaml` with overlays into `AppSettings` |
| `load_config(relative, model, ...)` | Load any `config/<relative>` YAML file with overlays into a Pydantic model |
| `SecretStore.from_environment()` | Resolve secrets from the process environment and the repository `.env` |
| `SecretStore.require_all(names)` | Return secrets as `SecretStr`; raise `MissingSecretError` naming every missing variable |
| `resolve_environment()` / `write_selected_environment()` | Choose the active environment (`dev`, `lab`, `ci`) |
| `StrictModel` | Base model for configuration: unknown keys rejected, instances frozen |
| `ConfigError`, `MissingSecretError` | Raised on invalid or incomplete configuration |

Layering for `config/<path>`: the base file, then an environment overlay
(`config/environments/<env>.yaml` for `app.yaml`, `config/<dir>/<stem>.<env>.yaml` for
other files), then the git-ignored machine-local overlay `config/local/<path>`.

## Configuration

| Source | Meaning |
|:--|:--|
| `config/app.yaml`, `config/environments/*.yaml`, `config/local/app.yaml` | Application settings |
| `FAULTLINE_ENV` | Overrides the selected environment |
| `FAULTLINE_CONFIG_DIR` | Overrides the location of `config/` |
| `.faultline/env` | Environment chosen with `faultline env use` (git-ignored) |
| Variables named in YAML (`*_env` keys) | Secrets, read from the environment or `.env` |

## Tests

Unit tests live in `tests/` and use temporary directories only:

```bash
uv run pytest packages/core/tests
make test-component C=packages/core
```
