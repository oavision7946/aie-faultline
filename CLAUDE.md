# aie-faultline

AI-powered failure analysis for distributed systems: ingest logs and traces, and use LLMs to help engineers find the likely root cause of a failure faster.

> **This file is public.** Keep it free of roadmap, customer, employer, and internal design details.

## Tech stack

- Python, with dependencies and environments managed by **uv**
- ClickHouse for logs and telemetry
- PostgreSQL (with pgvector) for operational data; SQLite for tests
- Pydantic for validating API input and output shapes
- LLM providers (Anthropic, OpenAI, local open-source models) are configured through an external YAML file. Never hard-code a provider or model.

## Commands

```bash
uv sync                          # install dependencies
uv run pytest                    # component unit tests only
uv run pytest apps/api/tests     # API tests (separate suite)
uv run pytest tests/integration  # integration tests (separate suite)
uv run pytest tests/e2e          # end-to-end tests (separate suite)
uv run ruff check .              # lint
uv run mypy .                    # static analysis
```

API, UI, integration, and end-to-end tests live apart from component unit tests and are run separately.

## Conventions

- Every component ships with unit tests, linting, static analysis, and documentation. Do not consider a component done without all four.
- Validate all API inputs and outputs with Pydantic models.
- Keep API and UI tests separate from unit tests.
- Configuration lives in YAML files in the `config/` folder.
- Secrets and authorization keys live in `.env` files and are never committed. Keep a `.env.example` with placeholder values only.
- Keep changes small and focused. Run tests and linters before committing.

## Public-repo hygiene

This repository is public. Treat everything you write into it as published.

- Do not put any of the following in tracked files (code, comments, docstrings, docs, README, test fixtures, commit messages, PR or issue text): roadmap or unreleased plans, customer names or data, employer names, or the reasoning behind internal design decisions.
- Test data must be synthetic or properly anonymized. Never commit real logs or traces from a customer or employer.
- `.internal/` and `CLAUDE.local.md` are gitignored. Never stage them, never use `git add -f` on them, and never remove their ignore rules.
- Write comments and docs in generic technical terms: what the code does and how to use it.
- If you need planning context and `CLAUDE.local.md` is not present, ask the user rather than guessing.
