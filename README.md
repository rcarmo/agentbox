# Agentbox - Coding Agent Sandbox

![Logo](docs/icon-256.png)

There's no perfect way to sandbox agents (yet), but containers are a practical start.

Agentbox is a Docker-based coding agent sandbox, originally inspired by [Batrachian Toad](https://github.com/batrachianai/toad), and now generalized to more tools.
It provides an isolated environment that works well with [`webterm`](https://github.com/rcarmo/webterm) for running multiple agent sessions.

## Features

The default container provides:

- **Development environment**: Debian Trixie with common development tools
- **Preinstalled coding agents**: [Copilot CLI](https://github.com/github/copilot-cli), [Codex](https://github.com/openai/codex), [Pi](https://github.com/nicholasgasior/pi-coding-agent)
- **Preinstalled CLI tools**: [gh](https://cli.github.com/), Nushell, `lazygit`, `killall`
- **Package managers**: Homebrew and APT, plus `uv` and Bun
- **Optional agent tooling**: install `toad`, `opencode`, `gemini`, and `vibe` via `make -C ~ ...`
- **Service control**: toggle Docker/SSH/RDP with `ENABLE_DOCKER`, `ENABLE_SSH`, and `ENABLE_RDP`
- **Docker-in-Docker**: available when containers run in privileged mode
- **Remote access**: SSH (`ENABLE_SSH=true`) and mosh support
- **Workspace bootstrap**: built-in workspace skeleton and agent skills under `/home/agent/workspace-skel`

## Roadmap

- [x] CPU and memory limits (basic Docker resource constraints)
- [ ] Network isolation options
- [ ] Other sandboxing techniques (gVisor, Kata Containers, etc.)

## Service Configuration

Agentbox uses environment variables to control which services start at container launch:

- `ENABLE_DOCKER=true` - Start Docker daemon (for Docker-in-Docker support)
- `ENABLE_SSH=true` - Start SSH server (port 22)
- `ENABLE_RDP=true` - Start RDP server (port 3389)
- `AGENTBOX_ENVIRONMENT=cli|gui` - Image-provided environment marker (`cli` for headless/CLI, `gui` for desktop images)

**Default behavior:** All services are disabled unless explicitly enabled.

### Examples:

```bash
# Default - all services disabled
docker run -d agentbox

# Enable only Docker daemon
docker run -d -e ENABLE_DOCKER=true agentbox

# Enable Docker and SSH for development
docker run -d -e ENABLE_DOCKER=true -e ENABLE_SSH=true -p 22:22 agentbox

# Full desktop experience with all services (GUI image)
docker run -d -e ENABLE_DOCKER=true -e ENABLE_SSH=true -e ENABLE_RDP=true -p 22:22 -p 3389:3389 agentbox:gui
```

## Quick Start

### Optional Tool Installs

Inside the container, the `agent` user ships with a `~/Makefile` that can install additional tooling.

**Coding agents/CLIs you can install via `make -C ~ …`:**

- `toad` — installs **Batrachian Toad** (via `uv tool`)
- `opencode` — installs **OpenCode** (via Bun)
- `gemini` — installs **Gemini CLI** (via Homebrew)
- `vibe` — installs **mistral-vibe** (via `uv tool`)

**Convenience targets:**

- `tools` — installs `node`, `go`, `gemini`, `vibe`
- `node`, `go` — install language toolchains (prereqs for some agents)

### Workspace skeleton

Agentbox ships a built-in project skeleton at `/home/agent/workspace-skel`.

To copy it into your current `/workspace` **without overwriting existing files**:

```bash
make init-workspace
```

See [docs/workspace-skeleton.md](docs/workspace-skeleton.md) for details.

### GUI Image

The GUI build is published as the `:gui` tag (also `<release>-gui`) and includes XFCE, XRDP, and VS Code.

### Docker Compose

Recommended workflow:

```bash
make up
make enter-toad   # or: make enter-copilot
make down
```

If you need service overrides, create `docker-compose.override.yml`:

```yaml
services:
  toad:
    environment:
      ENABLE_DOCKER: "true"
      ENABLE_SSH: "true"
  copilot:
    environment:
      ENABLE_DOCKER: "true"
      ENABLE_SSH: "true"
```

Then run:

```bash
docker compose up -d
```

### Using Docker Directly

```bash
# Build the headless image
docker build -t agentbox .

# Build the GUI image
docker build -t agentbox:gui --target gui .

# Run the container with selected services (GUI image)
docker run -d \
  --name agentbox \
  --privileged \
  -e ENABLE_DOCKER=true \
  -e ENABLE_SSH=true \
  -e ENABLE_RDP=true \
  -p 22:22 \
  -p 3389:3389 \
  -v $(pwd):/workspace \
  agentbox:gui
```

### Using Batrachian Toad

Once connected to the container:

1. Install Toad (if needed):

```bash
make -C ~ toad
```

2. Start Toad:

```bash
toad
```

3. Or start with a specific project directory:

```bash
toad /workspace
```

4. Or launch directly with an agent:

```bash
toad -a open-hands
```

## Security Notes

- **Service Control:** By default, all services (Docker, SSH, RDP) are disabled. Explicitly enable only what you need using environment variables.
- Default passwords are weak - change them for production use
- The container needs to run in privileged mode for Docker-in-Docker to be available to your agents (it's better than nothing)
- Consider using SSH keys instead of password authentication
- For production use, consider disabling unnecessary services and changing default credentials


## Credits

This project is loosely based on my ancient [rcarmo/docker-templates/desktop-chrome](https://github.com/rcarmo/docker-templates/tree/master/desktop-chrome) with an updated userland.

## License

MIT
