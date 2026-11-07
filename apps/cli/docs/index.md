# aie-faultline-cli

Command-line interface: `faultline`.

## Local stack

`faultline stack up` starts ClickHouse with Docker Compose (`infra/compose/compose.yaml`)
and Postgres with the Supabase CLI (`supabase/`), using ports, limits and image versions
from `config/app.yaml`. ClickHouse passwords are passed to the container from the
environment; the read-only user's query limits come from `clickhouse.readonly_limits`.

| Operation | Effect |
|:--|:--|
| `up` | Start and wait for health; create the ClickHouse database |
| `down` | Stop, keep data |
| `reset` | Stop, delete data volumes, start again |
| `db-reset` | Recreate Postgres from `supabase/migrations` and `supabase/seed.sql` |

## Host checks

- `gpu-check`: `nvidia-smi` reports a GPU and Docker has the `nvidia` runtime.
- `capacity-check`: free disk for the data directory is above `capacity.min_free_disk_gb`
  and the ClickHouse memory cap is below `capacity.max_clickhouse_memory_fraction` of RAM.

See the [API reference](reference.md).
