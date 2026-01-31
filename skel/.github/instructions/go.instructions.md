# Go project instructions

Applies when: this repo has `go.mod`.

## Makefile-first workflow
- CI should run `make deps`, `make check`, and `make test`.
- Put `golangci-lint` and `gosec` wiring behind Make targets.

## Conventions to implement
- `make test` should run `go test ./...` (prefer `-race` and coverage in CI).
- Avoid bespoke CI steps when a Make target can encode the same behavior.
