# Skill: Go project conventions

## Goal
Provide a standard Go workflow with module caching, linting, security checks, and tests driven by Make.

## Make targets (recommended)
- `make deps` → `go mod download` + install `golangci-lint` and `gosec` if missing
- `make vet` → `go vet ./...`
- `make lint` → `golangci-lint run --timeout=5m`
- `make security` → `gosec ./...`
- `make test` → `go test -v -race -coverprofile=coverage.out ./...`
- `make check` → `make vet && make lint`
