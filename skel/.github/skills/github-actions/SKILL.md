# Skill: GitHub Actions CI patterns

## Goal
Keep CI simple and repo-driven: workflows should call Make targets.

## Conventions
- Always include `actions/checkout@v4`.
- Prefer a single `make check` step.
- Keep language/tool setup minimal unless required.

## Files
- `.github/workflows/ci.yml`
- `.github/workflows/cleanup.yml`
