# Skill: Docker image publishing

## Goal
Provide a reusable GitHub Actions workflow to build/push multi-arch images to GHCR on tag pushes.

## Conventions
- Publish on tags `v*`.
- Use native Intel or ARM runners for CI/CD. Don't use QEMU
- Use buildx + per-arch digest builds, then merge into a manifest.
- Use `docker/metadata-action` for semver tag derivation.

## Files
- `.github/workflows/docker-publish.yml`
- `.github/workflows/prune-docker-images.yml`
