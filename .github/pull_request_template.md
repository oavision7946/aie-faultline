## Summary

<!-- What does this change do, and why? -->

## Checklist

- [ ] Tests added or updated in the right suite (component unit, API, integration, end-to-end)
- [ ] Lint, type check and unit tests pass locally
- [ ] Every new boundary (API, tool, configuration, LLM output) is a Pydantic model
- [ ] Documentation updated for every component touched
- [ ] Configuration changes are in `config/` YAML; no secret appears in code, YAML or logs
- [ ] Dependencies added through `uv` only
- [ ] No private or customer data in code, fixtures, docs or this description
