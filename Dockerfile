# Agent - Coding Agent Sandbox
FROM debian:bookworm-slim AS base

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    TERM=xterm-256color \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    HOME=/home/agent \
    AGENTBOX_ENVIRONMENT=cli

RUN echo "export AGENTBOX_ENVIRONMENT=${AGENTBOX_ENVIRONMENT}" > /etc/profile.d/agentbox-env.sh

WORKDIR /tmp

# Layer 1: Install all system packages (locales, core tools, Docker) in single apt transaction
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales tzdata && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    update-locale LANG=en_US.UTF-8 && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # Core utilities
    ca-certificates apt-transport-https gnupg curl wget unzip \
    bash-completion man rsync sudo less zsh \
    # Development tools
    git vim tmux htop tree ripgrep \
    # SSH/mosh server
    openssh-server mosh \
    # Network tools
    bmon net-tools iputils-ping dnsutils iproute2 \
    # Build essentials
    build-essential cmake make pkg-config \
    # Python dependencies
    python3-dev python3-pip python3-venv libssl-dev libffi-dev \
    lsb-release \
    # Process management tools
    psmisc procps && \
    # Install Docker
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/* && \
    # Generate SSH host keys and create directories
    ssh-keygen -A && \
    mkdir -p /run/sshd /var/run/sshd && chmod 755 /run/sshd /var/run/sshd

# Layer 2: Create user and skeleton directory
RUN useradd -m -s /bin/bash -G sudo,docker agent && \
    echo 'agent:smith' | chpasswd && \
    echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    mkdir -p /etc/skel.agent

# Layer 3: Create entrypoint-user.sh with home directory initialization
RUN cat > /entrypoint-user.sh <<'ENTRYPOINT_USER'
#!/bin/bash
set -e

MARKER_FILE="/home/agent/.container_initialized"

# Check if UID/GID changed since last initialization
uid_gid_changed() {
    if [ ! -f "$MARKER_FILE" ]; then
        return 0  # No marker = needs init
    fi
    
    # Compare against TARGET UID/GID (from env vars if set, else current)
    local target_uid="${PUID:-$(id -u agent 2>/dev/null)}"
    local target_gid="${PGID:-$(id -g agent 2>/dev/null)}"
    local stored=$(cat "$MARKER_FILE" 2>/dev/null || echo "")
    
    if [ "$stored" != "${target_uid}:${target_gid}" ]; then
        echo "UID/GID changed: was $stored, now ${target_uid}:${target_gid}"
        return 0  # Changed
    fi
    return 1  # Same
}

initialize_home() {
    local SKEL_DIR="/etc/skel.agent"
    local HOME_DIR="/home/agent"
    
    # Skip if already initialized (marker exists and .bashrc exists) and UID/GID unchanged
    if [ -f "$MARKER_FILE" ] && [ -f "$HOME_DIR/.bashrc" ] && ! uid_gid_changed; then
        echo "Home directory already initialized (fast path)"
        return 0
    fi
    
    echo "Checking home directory initialization..."
    
    if [ ! -f "$HOME_DIR/.bashrc" ]; then
        echo "Home directory appears empty (mounted volume), initializing from skeleton..."
        
        if [ -d "$SKEL_DIR" ] && [ "$(ls -A $SKEL_DIR 2>/dev/null)" ]; then
            cp -a "$SKEL_DIR/." "$HOME_DIR/"
            echo "Home directory initialized with configuration files"
        else
            echo "Warning: Skeleton directory is empty, creating minimal config"
            cat > "$HOME_DIR/.bashrc" <<'BASHRC'
case $- in *i*) ;; *) return;; esac
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s checkwinsize
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
fi
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
[ -d /home/linuxbrew/.linuxbrew ] && eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"
[ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"
[ -d "$HOME/.bun" ] && export BUN_INSTALL="$HOME/.bun" && export PATH="$BUN_INSTALL/bin:$PATH"
if [ -d "$HOME/.ssh" ] && [ -z "$SSH_AUTH_SOCK" ]; then
    eval "$(ssh-agent -s)" >/dev/null
fi
BASHRC
        fi
    else
        echo "Home directory already initialized"
    fi
    
    if [ ! -f "$HOME_DIR/.xsession" ] && [ -f "$SKEL_DIR/.xsession" ]; then
        cp -a "$SKEL_DIR/.xsession" "$HOME_DIR/.xsession"
        echo "Restored .xsession from skeleton"
    fi
    
    if [ ! -f "$HOME_DIR/.profile" ]; then
        cat > "$HOME_DIR/.profile" <<'PROFILE'
[ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"
[ -d "$HOME/bin" ] && PATH="$HOME/bin:$PATH"
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH"
PROFILE
    fi
    
    # Create symlinks to /config for persistent config files
    for item in .gitconfig .vibe .gemini .copilot .vimrc .tmux.conf; do
        target="/config/$item"
        link="$HOME_DIR/$item"
        if [ -e "$target" ] || [ -d "$target" ]; then
            rm -rf "$link" 2>/dev/null || true
            ln -sf "$target" "$link"
            echo "Linked $link -> $target"
        fi
    done
}

setup_user_ids() {
    if [ -n "$PUID" ] && [ -n "$PGID" ]; then
        echo "Setting up agent with UID=$PUID and GID=$PGID"
        usermod -o -u "$PUID" agent || true
        groupmod -o -g "$PGID" agent || true
        usermod -g "$PGID" agent || true
    fi
}

fix_ownership() {
    # Skip entirely if marker exists and UID/GID unchanged
    if [ -f "$MARKER_FILE" ] && ! uid_gid_changed; then
        echo "Ownership already configured (fast path)"
        return 0
    fi
    
    echo "Fixing ownership of user directories..."
    
    # Only chown /home/agent if ownership is wrong (check one file)
    if [ -d /home/agent ] && [ "$(stat -c %U /home/agent 2>/dev/null)" != "agent" ]; then
        echo "Fixing /home/agent ownership..."
        chown -R agent:agent /home/agent
    fi
    
    # /home/linuxbrew is set correctly at build time - never chown at runtime
    # (it's not mounted and contains thousands of files)
    
    # Only chown /workspace if FIX_WORKSPACE_OWNERSHIP=true (opt-in)
    if [ "${FIX_WORKSPACE_OWNERSHIP:-false}" = "true" ] && [ -d /workspace ]; then
        if [ "$(stat -c %U /workspace 2>/dev/null)" != "agent" ]; then
            echo "Fixing /workspace ownership (FIX_WORKSPACE_OWNERSHIP=true)..."
            chown -R agent:agent /workspace
        fi
    fi
}

mark_initialized() {
    # Store TARGET UID:GID (after setup_user_ids has run)
    echo "$(id -u agent):$(id -g agent)" > "$MARKER_FILE"
}

initialize_home
setup_user_ids
fix_ownership
mark_initialized
exec "$@"
ENTRYPOINT_USER
RUN chmod +x /entrypoint-user.sh

# Layer 4: Install Homebrew, Copilot, Bun, UV, and optional tools Makefile as agent
USER agent
WORKDIR /home/agent
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && \
    echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc && \
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)" && \
    brew update && brew install copilot-cli nushell && \
    curl -fsSL https://bun.sh/install | bash && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && \
    echo 'source "$HOME/.local/bin/env"' >> ~/.bashrc && \
    echo 'if [ -d "$HOME/.ssh" ] && [ -z "$SSH_AUTH_SOCK" ]; then' >> ~/.bashrc && \
    echo '    eval "$(ssh-agent -s)" >/dev/null' >> ~/.bashrc && \
    echo 'fi' >> ~/.bashrc && \
    cat > ~/Makefile <<'MAKEFILE'
.PHONY: tools node go gemini vibe all
BREW ?= /home/linuxbrew/.linuxbrew/bin/brew
UV ?= $(HOME)/.local/bin/uv

tools: node go gemini vibe
node:
	$(BREW) install node

go:
	$(BREW) install golang

gemini:
	$(BREW) install gemini-cli

vibe:
	$(UV) tool install -U mistral-vibe

all: tools
MAKEFILE

# Layer 5: Save skeleton
USER root
RUN cp -a /home/agent/. /etc/skel.agent/ && \
    echo "Skeleton: $(find /etc/skel.agent -type f | wc -l) files"

# Layer 7: Create all runtime scripts
RUN cat > /entrypoint.sh <<'ENTRYPOINT'
#!/bin/bash
set -euo pipefail
echo "=== Agent Coding Agent Sandbox ==="
echo "User: agent | SSH Password: smith | RDP: port 3389"
echo ""
[ "${ENABLE_DOCKER:-false}" = "true" ] && echo "Starting Docker..." && /etc/init.d/docker start || echo "Docker disabled"
[ "${ENABLE_SSH:-false}" = "true" ] && echo "Starting sshd..." && /usr/sbin/sshd || echo "SSH disabled"
if [ "${ENABLE_RDP:-false}" = "true" ]; then
    if [ -x /quickstart.sh ]; then
        echo "Starting xrdp..."
        exec /quickstart.sh
    else
        echo "RDP requested but GUI stack is not installed in this image."
        exit 1
    fi
else
    echo "RDP disabled. Container idle..."
    tail -f /dev/null
fi
ENTRYPOINT
RUN chmod +x /entrypoint.sh

EXPOSE 22 3389
ENTRYPOINT ["/entrypoint-user.sh", "/entrypoint.sh"]


FROM base AS gui
ENV AGENTBOX_ENVIRONMENT=gui
RUN echo "export AGENTBOX_ENVIRONMENT=${AGENTBOX_ENVIRONMENT}" > /etc/profile.d/agentbox-env.sh
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    xfce4 xfce4-goodies firefox-esr \
    xrdp xorgxrdp \
    lxterminal pcmanfm lxpanel \
    gtk2-engines-pixbuf elementary-icon-theme \
    fonts-dejavu fonts-inter fonts-noto fonts-roboto fonts-liberation \
    xclip x11-utils x11-xserver-utils \
    dbus-x11 xdg-utils xterm && \
    apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

USER agent
RUN cat > ~/.xsession <<'XSESSION'
#!/bin/sh
[ -f /etc/profile.d/agentbox-env.sh ] && . /etc/profile.d/agentbox-env.sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR
command -v dbus-launch >/dev/null 2>&1 && eval $(dbus-launch --sh-syntax)
[ -r $HOME/.Xresources ] && xrdb $HOME/.Xresources
xsetroot -solid grey
exec startxfce4
XSESSION
RUN chmod +x ~/.xsession && \
    cat > ~/.Xresources <<'XRESOURCES'
Xft.dpi: 96
Xft.antialias: true
Xft.hinting: true
Xft.hintstyle: hintslight
Xft.rgba: rgb
XTerm*faceName: DejaVu Sans Mono
XTerm*faceSize: 11
XTerm*background: #1e1e1e
XTerm*foreground: #d4d4d4
XTerm*cursorColor: #d4d4d4
XTerm*saveLines: 10000
XTerm*scrollBar: false
XRESOURCES

USER root
RUN ARCH="$(dpkg --print-architecture)" && \
    case "$ARCH" in \
        amd64) VS_DEB_URL="https://update.code.visualstudio.com/latest/linux-deb-x64/stable" ;; \
        arm64) VS_DEB_URL="https://update.code.visualstudio.com/latest/linux-deb-arm64/stable" ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    wget "$VS_DEB_URL" -O /tmp/vscode.deb && \
    dpkg -i /tmp/vscode.deb && rm /tmp/vscode.deb && \
    cp -a /home/agent/. /etc/skel.agent/ && \
    echo "Skeleton: $(find /etc/skel.agent -type f | wc -l) files"

RUN cat > /etc/xrdp/startwm.sh <<'STARTWM'
#!/bin/bash
set -e
[ -f /etc/profile.d/agentbox-env.sh ] && . /etc/profile.d/agentbox-env.sh
sleep 1
export DISPLAY=${DISPLAY:-:10}
export PATH="$HOME/.local/bin:$PATH"
export XDG_RUNTIME_DIR=/tmp/runtime-$(whoami)
mkdir -p $XDG_RUNTIME_DIR && chmod 700 $XDG_RUNTIME_DIR
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS
command -v dbus-launch >/dev/null 2>&1 && eval $(dbus-launch --sh-syntax)
xsetroot -solid grey || true
exec startxfce4
STARTWM
RUN chmod +x /etc/xrdp/startwm.sh && \
    cat > /quickstart.sh <<'QUICKSTART'
#!/bin/bash
set -euo pipefail
rm -rf /tmp/.X* /tmp/ssh-* || true
mkdir -p /var/run/xrdp && chown xrdp:xrdp /var/run/xrdp
/usr/sbin/xrdp-sesman
/usr/sbin/xrdp --nodaemon &
XRDP_PID=$!
echo "xrdp started on port 3389"
echo "Connect: Username=agent Password=smith"
wait $XRDP_PID
QUICKSTART
RUN chmod +x /quickstart.sh

FROM base AS headless
ENV AGENTBOX_ENVIRONMENT=cli
