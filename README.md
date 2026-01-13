# Toadbox - Coding Agent Sandbox

![Toadbox Logo](docs/icon-256.png)

There's no perfect way to sandbox agents (yet), but at least we can try limiting the damage using containers.

Toadbox is a simple Docker-based coding agent sandbox featuring [Batrachian Toad](https://github.com/batrachianai/toad) as a general-purpose coding assistant TUI, which will help you boostrap pretty much _any_ current AI agent.

The container provides a Debian userland, Homebrew, (optional) Docker-in-Docker, `ssh`/`mosh` server, and a minimal RDP desktop environment.

## Motivation

I found myself wanting to quickly spin up isolated coding environments for AI agents, without having to deal with complex orchestration tools or heavy VMs, and also wanting to limit CPU usage from [Batrachian Toad](https://github.com/batrachianai/toad) itself.

## Features

- **[Batrachian Toad](https://github.com/batrachianai/toad)**: A unified interface for AI in your terminal
- **Development Environment**: Debian Bookworm with essential development tools
- **Visual Studio Code**: for ARM/Intel
- **Package Managers**: Homebrew and APT package management 
- **Docker-in-Docker**: Docker support for containerized workflows (requires you to run the container in privileged mode, so be careful)
- **Remote Access**: SSH (port 2222) and RDP (port 3390) connectivity
- **Minimal Desktop**: XFCE desktop with minimal utilities, so you can run graphical applications, Playwright, etc.
- **Persistent Storage**: optional data and agent home directory persistence

## Roadmap

- [x] CPU and memory limits (basic Docker resource constraints)
- [ ] Network isolation options
- [ ] Other sandboxing techniques (gVisor, Kata Containers, etc.)

## Quick Start

### Using Toadbox Manager (still WIP)

![Instance Manager](docs/screenshot.svg)

The Toadbox Manager is a first stab at a TUI for easily managing multiple toadbox instances with automatic naming, folder picker, and proper permission handling.

1. Clone or download this repository
2. Run the quick start script:

```bash
./run-manager.sh
```

**Manager Features:**

- 📁 **Folder Picker**: Browse and select workspace directories easily
- 🏷️ **Automatic Naming**: Container names and hostnames based on folder names
- 👤 **PUID/PGID Support**: Automatic permission alignment with host system
- 🐳 **Docker Compose**: Leverages docker-compose for orphan cleanup and resource management
- 🔄 **Multi-Instance**: Manage multiple development environments simultaneously

**Manager Usage:**

- Use arrow keys to navigate instances
- Press `c` to create a new instance
- Press `enter` to connect to selected instance
- Press `s` to start/stop instances
- Press `q` to quit

### Using Docker Compose (Manual)

If you prefer to use docker-compose directly:

1. Clone or download this repository
2. Run the container:

```bash
docker-compose up -d
```

3. Connect to the container:

**Via RDP (Graphical Desktop):**

- RDP Client: `localhost:3390`
- Username: `agent`
- Password: `changeme`

**Via SSH (Terminal):**

```bash
ssh agent@localhost -p 2222
# Password: changeme
```

### Using Docker Directly

```bash
# Build the image
docker build -t toadbox .

# Run the container
docker run -d \
  --name toadbox \
  --privileged \
  -p 2222:22 \
  -p 3389:3389 \
  -v $(pwd):/workspace \
  toadbox
```

### Using Batrachian Toad

Once connected to the container:

1. Start Toad:

```bash
toad
```

2. Or start with a specific project directory:

```bash
toad /workspace
```

3. Or launch directly with an agent:

```bash
toad -a open-hands
```

## Security Notes

- Default passwords are weak - change them for production use
- The container needs to run in privileged mode for Docker-in-Docker to be available to your agents (it's better than nothing)
- Consider using SSH keys instead of password authentication

For extra (in)security, consider running the manager with a remote Docker socket to a VM where the actual containers run.

## Credits

This project is loosely based on my ancient [rcarmo/docker-templates/desktop-chrome](https://github.com/rcarmo/docker-templates/tree/master/desktop-chrome) with an updated userland.

## License

MIT