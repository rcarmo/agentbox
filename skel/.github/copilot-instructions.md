# Copilot instructions (skeleton)

This is a starter template for repositories created inside Agentbox.

## Mandatory: use the Makefile

Use `make` targets for build/lint/test/format/dev flows whenever available.
If you need a new workflow step, add a Make target rather than running ad-hoc commands.

## Common workflows (expected Make targets)

- `make help` — list targets
- `make install` / `make install-dev` — install dependencies
- `make lint` / `make format` — static checks / formatting
- `make test` — run tests
- `make coverage` — run tests with coverage (if available)
- `make check` — run the project’s standard validation pipeline
- `make clean` — remove local build/test artifacts

## CI/CD convention

CI should call `make check` (or `make lint` + `make test` when `check` doesn’t exist).
Keep CI logic minimal; prefer Make targets for consistency.
