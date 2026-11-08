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
| `CLICKHOUSE_WRITER_PASSWORD`, `CLICKHOUSE_READONLY_PASSWORD` | Passwords for the two ClickHouse users; any random string works, for example the output of `openssl rand -hex 24` (a different value for each) |
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

Both services publish their ports only on `bind_host` (default `127.0.0.1`).

PostgreSQL runs on a Docker network named `faultline-supabase`, which `make up` creates
with `bind_host` as its host binding. Docker's daemon-wide `ip` option does not cover
networks like this one, so the network setting is what keeps the port local. After
starting, `make up` checks the published ports. If any of them listens on every
interface, it stops PostgreSQL and reports an error.

If you change `bind_host`, first stop PostgreSQL and remove the old network with
`docker network rm faultline-supabase`. A wildcard `bind_host` such as `0.0.0.0` is
refused for PostgreSQL unless you accept the exposure in `config/local/app.yaml`:

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
