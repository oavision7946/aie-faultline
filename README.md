# AI Engineering: Failure Analysis for Distributed Systems

> **Status:** early development. APIs and configuration will change.

## What it does

aie-faultline ingests logs and traces from distributed systems and uses LLMs to help engineers find the likely root cause of a failure faster.

## Features

Implemented so far:

- A `uv` workspace of components, each with unit tests, linting, strict type checking and documentation
- Typed YAML configuration with per-environment overlays and fail-fast secret handling
- A YAML registry of LLM providers and models (Anthropic, OpenAI, local OpenAI-compatible servers)
- A local service stack: ClickHouse with separate writer and read-only users, and PostgreSQL with pgvector

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Docker with Compose, and the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)
- An API key for at least one LLM provider, or a local open-source model
- GNU Make

## Quickstart

```bash
git clone https://github.com/oavision7946/aie-faultline.git
cd aie-faultline
cp .env.example .env        # fill in the values
make setup                  # dependencies, git hooks, prerequisite check
make up                     # start ClickHouse and PostgreSQL
make check                  # the full local quality gate
```

See [docs/runbooks/local-setup.md](docs/runbooks/local-setup.md) for details and troubleshooting.

## Configuration

- **Settings** are YAML files in `config/`: `app.yaml` plus overlays in `config/environments/` (`dev`, `lab`, `ci`). Select one with `make env-use ENV=dev`.
- **Machine-specific values** go in `config/local/`, which is git-ignored.
- **Secrets** (API keys and other credentials) go in `.env`, which is never committed. YAML names the variable; `.env.example` lists them all.
- **LLM providers** are defined in `config/llm/providers.yaml`, so you can switch providers and models without code changes.

## Development

```bash
make help              # all targets
make check             # format, lint, type check, security analysis, repository checks, unit tests
make test-api          # API tests (separate suite)
make test-integration  # integration tests (needs `make up`)
make docs              # build every component's docs with warnings as errors
```

Component unit tests also run with a bare `uv run pytest`. API, UI, integration and end-to-end tests live in separate folders and run separately. New components are created with `uv run python scripts/new_component.py packages <name> --description "..."`.

## Documentation

- Each component has a `README.md` and a `docs/` folder.
- Generic runbooks are in [`docs/runbooks/`](docs/runbooks/); dataset cards will be in [`docs/datasets/`](docs/datasets/).

## Contributing

Contributions are welcome. Please open an issue to discuss larger changes before sending a pull request. Every component needs unit tests, linting, static analysis, and documentation, and `make check` must pass.

## License

[MIT](LICENSE)
