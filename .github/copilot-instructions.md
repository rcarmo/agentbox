# Copilot instructions for this repository

This repo builds **Agentbox**: a Docker image (plus an optional GUI target) for running coding agents in an isolated container environment, and a `docker-compose.yml` that spins up example agent workspaces.

## Build / test / lint

There is no unit test suite or linter configured in this repository.

### Common commands

- Show available Make targets:
  - `make help`

- Start the example multi-container setup (syncthing + agent containers):
  - `make up`

- Stop it:
  - `make down`

- Build the Docker image locally (headless/CLI):
  - `docker build -t agentbox .`

- Build the GUI variant locally:
  - `docker build -t agentbox:gui --target gui .`

### CI build (reference)

GitHub Actions builds and pushes multi-arch images on tag pushes:
- Workflow: `.github/workflows/publish.yml`
- Produces:
  - `ghcr.io/<owner>/<repo>:<tag>` and `:latest`
  - `ghcr.io/<owner>/<repo>:<tag>-gui` and `:gui`

## High-level architecture

- **Docker image is the product**
  - `Dockerfile` defines a multi-stage build:
    - `base`: Debian Bookworm + core tooling, user creation (`agent`), entrypoints.
    - `gui`: installs XFCE + XRDP + VS Code and sets up X session scripts.
    - `headless`: alias target that keeps the CLI environment.

- **Runtime behavior is controlled via env vars**
  - The container entrypoint is `/entrypoint-user.sh` → `/entrypoint.sh`.
  - `/entrypoint-user.sh` handles first-run home initialization, UID/GID adjustment, and optional ownership fixes.
  - `/entrypoint.sh` starts services based on env vars (Docker-in-Docker, SSH, RDP); otherwise it idles.

- **`docker-compose.yml` is an example orchestration**
  - `syncthing` shares `./workspaces` on the host.
  - `toad` and `copilot` are example agent containers mounting specific subfolders under `./workspaces/<name>` to `/workspace`.
  - Compose uses resource limits and runs the agent containers as `privileged: true` to enable Docker-in-Docker when requested.

## Key conventions (repo-specific)

- **Versioning and releases**
  - The repo version is stored in `VERSION`.
  - `make bump-patch` updates `VERSION`, commits, and tags `v<new_version>`.
  - CI is tag-driven: pushing a tag triggers the Docker publish workflow.

- **Agent user + persistence model**
  - Default user inside the container is `agent` (member of `sudo` and `docker`).
  - The container is designed for persistent config via `/config`:
    - At runtime, common dotfiles are symlinked from `/config` into `/home/agent` when present (see `Dockerfile` loop for `.gitconfig`, `.copilot`, etc.).

- **Home initialization is optimized**
  - `/entrypoint-user.sh` writes a marker file (`/home/agent/.container_initialized`) containing `uid:gid` and uses it to skip expensive re-initialization when possible.

- **Ownership changes are intentionally constrained**
  - `/workspace` ownership is only fixed when `FIX_WORKSPACE_OWNERSHIP=true` (opt-in), to avoid large recursive `chown` operations on mounted volumes.

- **Important env vars used across Dockerfile/README/compose**
  - Service toggles:
    - `ENABLE_DOCKER=true` (Docker-in-Docker)
    - `ENABLE_SSH=true`
    - `ENABLE_RDP=true` (GUI image only)
  - Identity mapping:
    - `PUID`, `PGID` (compose defaults to 1000)
  - Image marker:
    - `AGENTBOX_ENVIRONMENT=cli|gui`

