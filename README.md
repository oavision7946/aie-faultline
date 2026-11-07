# AI Engineering: Failure Analysis for Distributed Systems

> **Status:** early development. APIs and configuration will change.

## What it does

aie-faultline ingests logs and traces from distributed systems and uses LLMs to help engineers find the likely root cause of a failure faster.

### The problem

When a distributed system fails, the signal is buried. The engineer on call faces thousands of log lines, traces and metrics spread across many services, and the component raising the loudest alarm is often not the one that broke. aie-faultline turns that noise into a short, evidence-backed hypothesis: what is abnormal, where it started, why it most likely happened, and what to check next.

### How it works

aie-faultline works in layers, so each kind of work goes to the right tool:

- **Always-on detection.** Lightweight models watch the telemetry stream and flag behavior that looks abnormal.
- **Correlation.** Service topology and timing link signals across components, showing where a failure began and how it spread.
- **Investigation.** An LLM-driven agent is brought in only for incidents that matter. It decides which evidence to pull, tests competing explanations, and reports a conclusion linked to the exact log records and traces behind it.

Reasoning is reserved for the moments that need it, so no LLM ever has to read every log line.

### The questions it answers

1. **Is something wrong?** Spot abnormal behavior early.
2. **What kind of failure is it?** Put the problem in a known category.
3. **Where is it?** Rank the components most likely involved.
4. **What started it?** Separate the initiating cause from the symptoms that followed. The first component to look unhealthy is a clue, not proof.
5. **What should an engineer do next?** Suggest next steps with a confidence level. It recommends; it never changes the system.

### Built on open data

The project is developed and evaluated against public datasets of logs, traces, metrics and labeled incidents. Those datasets are replayed in event time as if they were live, so anyone can reproduce the results without access to a production system.

### Principles

- **Evidence first.** Every claim points to records you can inspect yourself.
- **The right model for the job.** Inexpensive models run continuously; expensive reasoning runs on demand.
- **Honest about uncertainty.** Answers come with a confidence level, and the system says so when the evidence is not enough.
- **Recommend, don't act.** Diagnosis and remediation stay separate, and people stay in control.
- **Logs are untrusted input.** Investigation tools are read-only, and log text is treated as data, never as instructions.

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
