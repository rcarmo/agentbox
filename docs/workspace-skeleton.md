# Workspace skeleton

Agentbox ships a built-in **workspace skeleton** intended to jump-start new repositories with:

- A baseline `.github/` folder (CI, release, Docker publishing, cleanup)
- Stack-specific Copilot instruction files under `.github/instructions/`
- A `copilot-instructions.md` tuned for “use the Makefile” workflows
- A template `Makefile`
- `SKILL.md` files under `.github/skills/` that document the intended conventions

## Where it lives in the container

The skeleton is copied into:

- `/home/agent/workspace-skel/`

## How to initialize a new workspace

From inside the container:

```bash
make init-workspace
```

This copies `/home/agent/workspace-skel/` into `/workspace/` **without overwriting existing files**.

## What gets copied

- `Makefile`
- `.github/copilot-instructions.md`
- `.github/workflows/` (CI, release, Docker publish, cleanup)
- `.github/instructions/` (stack-specific Copilot instructions)
- `.github/skills/` (skill descriptions)

## Notes

- The workflows are intentionally generic and expect projects to provide meaningful `make check` (or `make lint` + `make test`) targets.
- Docker publishing workflows are geared towards pushing to GHCR on tags `v*`.
