# Skill: Frontend bundling via Bun/Node

## Goal
Provide optional Make targets for TypeScript typecheck + bundling (Bun preferred).

## Recommended targets
- `node_modules` / `make deps-frontend` to install deps
- `make typecheck`
- `make build` (typecheck + bundle)
- `make build-fast` (bundle only)
- `make bundle-watch`
- `make bundle-clean`
