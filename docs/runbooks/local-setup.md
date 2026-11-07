# Local setup

## Prerequisites

| Tool | Check |
|:--|:--|
| uv | `uv --version` |
| Docker with Compose | `docker compose version` |
| Supabase CLI | `supabase --version` |
| GNU Make | `make --version` |

## First run

```bash
cp .env.example .env          # then fill in the values
make setup                    # installs dependencies and git hooks, validates config
make env-use ENV=dev          # or lab / ci
make up                       # ClickHouse + PostgreSQL, waits until healthy
make reset-gate               # database reset twice, verified each time
make test-integration
```

## Secrets

Set at least these in `.env`:

| Variable | Used for |
|:--|:--|
| `CLICKHOUSE_WRITER_PASSWORD`, `CLICKHOUSE_READONLY_PASSWORD` | Passwords for the two ClickHouse users; choose any strong values |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | The local Supabase database credentials |
| `ANTHROPIC_API_KEY` (and others in use) | LLM providers enabled for your environment |

`make llm-check` reports which provider keys are missing.

## Ports and addresses

Ports and the bind address are settings in `config/app.yaml`. To change them for one
machine only, create `config/local/app.yaml`, for example:

```yaml
clickhouse:
  http_port: 18123
  native_port: 19000
postgres:
  port: 55432
```

ClickHouse publishes its ports on `bind_host` (default `127.0.0.1`).

The Supabase CLI publishes PostgreSQL on Docker's default bind address, which is all
interfaces unless Docker is configured otherwise. `make up` refuses to start PostgreSQL in
that case. Either set Docker's default bind address (the `ip` option of the Docker daemon
configuration) to `127.0.0.1`, or, if the machine is not reachable from other networks,
accept the exposure in `config/local/app.yaml`:

```yaml
postgres:
  allow_wildcard_bind: true
```

## Troubleshooting

| Symptom | Fix |
|:--|:--|
| `Missing required secret(s): ...` | Add the named variables to `.env` |
| `port is already allocated` | Another service uses the port; change it in `config/local/app.yaml` |
| `Docker publishes ports on 0.0.0.0 ...` | See "Ports and addresses" above |
| ClickHouse unhealthy | `docker logs faultline-clickhouse`; check the memory limit in config |
| Start from scratch | `make reset` deletes local data and starts again |
