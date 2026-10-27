# aie-faultline

**AI-powered failure analysis for distributed systems.**

> **Status:** early development. APIs and configuration will change.

<!-- TODO: badges (CI, license, Python version) -->

## What it does

aie-faultline ingests logs and traces from distributed systems and uses LLMs to help engineers find the likely root cause of a failure faster.

<!-- TODO: add a short demo, screenshot, or example output -->

## Features

<!-- TODO: list only what is implemented today -->

- TODO

## Requirements

- Python (TODO: minimum version)
- [uv](https://docs.astral.sh/uv/) for dependency and environment management
- ClickHouse and PostgreSQL with pgvector (TODO: document local setup)
- An API key for at least one LLM provider, or a local open-source model

## Quickstart

```bash
git clone https://github.com/<org>/aie-faultline.git
cd aie-faultline
uv sync
cp .env.example .env        # add your API keys
# TODO: first command to run the project
```

## Configuration

- **Settings** are YAML files in `config/`.
- **Secrets** (API keys and other credentials) go in `.env`, which is never committed.
- **LLM providers** (Anthropic, OpenAI, local open-source models) are defined in an external YAML file, so you can switch providers without code changes.

<!-- TODO: link to full configuration reference in docs/ -->

## Development

```bash
uv run pytest tests/unit    # unit tests
uv run ruff check .         # lint
uv run mypy .               # static analysis
```

<!-- TODO: confirm commands; describe how to run API/UI tests, which are kept separate from unit tests -->

## Documentation

See the [`docs/`](docs/) folder. <!-- TODO -->

## Contributing

Contributions are welcome. Please open an issue to discuss larger changes before sending a pull request. Every component needs unit tests, linting, static analysis, and documentation.

<!-- TODO: CONTRIBUTING.md, code of conduct -->

## License

<!-- TODO: choose a license and add a LICENSE file -->
