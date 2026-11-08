# aie-faultline-cli

Command-line interface.

**Status:** environment, configuration, LLM check, local stack and host-check commands.

## Interface

The `faultline` command (`uv run faultline --help`):

| Command | Purpose |
|:--|:--|
| `faultline env use <dev\|lab\|ci>` / `env show` | Select the environment / print effective settings (no secrets) |
| `faultline config validate` | Validate every config file for every environment |
| `faultline llm check` | Check providers enabled in the selected environment |
| `faultline stack up\|down\|reset [clickhouse] [postgres]` | Manage the local stack |
| `faultline stack status` / `stack db-reset` | Show status / recreate Postgres from migrations and seed |
| `faultline gpu-check` / `capacity-check` | Verify GPU access / disk space and memory caps |

`--env` overrides the selected environment for one command. The `Makefile` wraps these
commands (`make up`, `make llm-check`, ...).

The Postgres stack runs on the Docker network `faultline-supabase`, which `stack up` creates
with `bind_host` as its host binding. After starting, `stack up` checks the published
ports. If any of them listens on every interface, it stops Postgres and fails. A wildcard
`bind_host` is refused unless `postgres.allow_wildcard_bind` is true.

## Configuration

Reads settings and secrets only through `faultline_core.config`: `config/app.yaml` and
overlays, `config/llm/providers.yaml`, and the secret variables they name
(`CLICKHOUSE_WRITER_PASSWORD`, `CLICKHOUSE_READONLY_PASSWORD`, provider keys).
External tools used: `docker` (with Compose), `supabase`, `nvidia-smi` (GPU check only).

## Tests

Unit tests use a fake command runner; no Docker or network is needed:

```bash
uv run pytest apps/cli/tests
make test-component C=apps/cli
```
