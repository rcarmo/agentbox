# Docker image project instructions

Applies when: this repo builds/publishes a Docker image.

## CI/CD
- Use `.github/workflows/docker-publish.yml` (multi-arch by digest + manifest merge) as the baseline.
- Tags `v*` are the release boundary.

## Conventions
- Keep Docker build args/env documented in README.
- Prefer reproducible builds (minimize network fetches at runtime; pin versions when practical).
