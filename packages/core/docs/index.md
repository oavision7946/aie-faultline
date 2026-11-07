# aie-faultline-core

Domain models, identifiers and shared configuration support.

## Configuration loading

Settings are YAML files under `config/`, validated by Pydantic models with unknown keys
rejected. Each file is read in layers, later layers winning:

1. `config/<path>`
2. the environment overlay: `config/environments/<env>.yaml` for `app.yaml`, otherwise
   `config/<dir>/<stem>.<env>.yaml`
3. `config/local/<path>`, a git-ignored folder for values specific to one machine

Mappings merge recursively; lists and scalars are replaced.

## Secrets

YAML never holds secret values; it names the environment variable that does (keys ending
in `_env`). `SecretStore` reads the process environment and the repository's `.env` file,
with the process environment taking precedence. Values are returned as `SecretStr`, and a
missing secret raises `MissingSecretError`, whose message lists variable names only.

```python
from faultline_core.config import SecretStore, load_settings

settings = load_settings()
secrets = SecretStore.from_environment()
password = secrets.require(settings.clickhouse.writer_password_env)
```

See the [API reference](reference.md).
