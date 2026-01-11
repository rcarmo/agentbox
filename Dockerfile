# Toadbox - Coding Agent Sandbox
FROM debian:bookworm-slim

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Set working directory
WORKDIR /tmp

# Install locale package first
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    update-locale LANG=en_US.UTF-8 && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Basic system update and install core utilities
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # Core utilities
    ca-certificates \
    apt-transport-https \
    gnupg \
    curl \
    wget \
    unzip \
    bash-completion \
    man \
    rsync \
    sudo \
    locales \
    # Development tools
    git \
    vim \
    tmux \
    htop \
    # SSH/mosh server
    openssh-server \
    mosh \
    # Network tools
    net-tools \
    iputils-ping \
    dnsutils \
    # Build essentials
    build-essential \
    cmake \
    pkg-config \
    # Python dependencies
    python3-dev \
    python3-pip \
    python3-venv \
    libssl-dev \
    libffi-dev \
    # Cleanup
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Generate SSH host keys
RUN ssh-keygen -A

# Create user account 
RUN useradd -m -s /bin/bash -G sudo agent && \
    echo 'agent:changeme' | chpasswd && \
    echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Set up entrypoint to handle PUID/PGID properly
RUN echo '#!/bin/bash' > /entrypoint-user.sh && \
    echo 'set -e' >> /entrypoint-user.sh && \
    echo '' >> /entrypoint-user.sh && \
    echo '# Simple PUID/PGID setup' >> /entrypoint-user.sh && \
    echo 'if [ -n "$PUID" ] && [ -n "$PGID" ]; then' >> /entrypoint-user.sh && \
    echo '    echo "Setting up agent with UID=$PUID and GID=$PGID"' >> /entrypoint-user.sh && \
    echo '    # Update user UID and GID' >> /entrypoint-user.sh && \
    echo '    usermod -o -u "$PUID" agent || true' >> /entrypoint-user.sh && \
    echo '    groupmod -o -g "$PGID" agent || true' >> /entrypoint-user.sh && \
    echo '    usermod -g "$PGID" agent || true' >> /entrypoint-user.sh && \
    echo '    # Fix ownership of user directories' >> /entrypoint-user.sh && \
    echo '    chown -R agent:agent /home/agent || true' >> /entrypoint-user.sh && \
    echo '    chown -R agent:agent /home/linuxbrew || true' >> /entrypoint-user.sh && \
    echo '    [ -d /workspace ] && chown -R agent:agent /workspace || true' >> /entrypoint-user.sh && \
    echo 'fi' >> /entrypoint-user.sh && \
    echo '' >> /entrypoint-user.sh && \
    echo 'exec "$@"' >> /entrypoint-user.sh && \
    chmod +x /entrypoint-user.sh

# Set user home
ENV HOME=/home/agent

# Install Homebrew
USER agent
WORKDIR /home/agent
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && \
    echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> /home/agent/.bashrc && \
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)" && \
    brew update

# Switch back to root for Docker installation
USER root
WORKDIR /tmp

# Install Docker (Docker in Docker support)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    usermod -aG docker agent

# Install xrdp and minimal desktop
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # xrdp for remote desktop
    xrdp \
    xorgxrdp \
    # Window manager
    openbox \
    # Terminal emulator
    lxterminal \
    # File manager
    pcmanfm \
    # Panel/taskbar
    lxpanel \
    # Theme and icons
    gtk2-engines-pixbuf \
    elementary-icon-theme \
    # Fonts
    fonts-dejavu \
    fonts-inter \
    fonts-noto \
    fonts-roboto \
    fonts-liberation \
    # Clipboard support for Toad
    xclip \
    # X11 utilities
    x11-utils \
    x11-xserver-utils \
    # D-Bus (required for desktop session)
    dbus-x11 \
    # Terminal fallback
    xterm \
    # Cleanup
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install UV (Python package manager)
USER agent
WORKDIR /home/agent
RUN curl -LsSf https://astral.sh/uv/install.sh | HOME=/home/agent sh && \
    echo 'export PATH="/home/agent/.local/bin:$PATH"' >> /home/agent/.bashrc && \
    echo 'source /home/agent/.local/bin/env' >> /home/agent/.bashrc && \
    /home/agent/.local/bin/uv tool install -U batrachian-toad

# Set up xrdp session configuration
USER agent
WORKDIR /home/agent
RUN mkdir -p ~/.config/openbox && \
    cat > ~/.xsession <<'XSESSION'
#!/bin/sh
# xrdp session script
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Set up runtime dir for dbus
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

# Start dbus session
if command -v dbus-launch >/dev/null 2>&1; then
    eval $(dbus-launch --sh-syntax)
fi

# X resources and background
[ -r $HOME/.Xresources ] && xrdb $HOME/.Xresources
xsetroot -solid grey

# Start panel and terminal in background
lxpanel &
lxterminal &

# Run openbox in foreground
exec openbox
XSESSION
RUN chmod +x ~/.xsession

# Runtime scripts (modeled after rcarmo/docker-templates desktop-chrome)
USER root

# Configure xrdp to use agent's .xsession
RUN cat > /etc/xrdp/startwm.sh <<'STARTWM'
#!/bin/bash
set -e

# Wait for X to be ready
sleep 1

# Set up DISPLAY if not set
export DISPLAY=${DISPLAY:-:10}

# Ensure agent-local tools (like toad) are on PATH
export PATH="$HOME/.local/bin:$PATH"

# Set up runtime dir
export XDG_RUNTIME_DIR=/tmp/runtime-$(whoami)
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

# Unset problematic variables
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Start dbus session
if command -v dbus-launch >/dev/null 2>&1; then
    eval $(dbus-launch --sh-syntax)
fi

# Set background
xsetroot -solid grey || true

# Start panel and terminal in background
lxpanel &
lxterminal &

# Run openbox in foreground - this keeps the session alive
exec openbox
STARTWM
RUN chmod +x /etc/xrdp/startwm.sh

# Ensure sshd can start
RUN mkdir -p /run/sshd /var/run/sshd && chmod 755 /run/sshd /var/run/sshd

# Start xrdp, keep the container alive
RUN cat > /quickstart.sh <<'EOF'
#!/bin/bash
set -euo pipefail

# cleanup /tmp
rm -rf /tmp/.X* /tmp/ssh-* || true

# Ensure xrdp can write to its directories
mkdir -p /var/run/xrdp
chown xrdp:xrdp /var/run/xrdp

# Create .xsession for agent if it doesn't exist (home is a volume)
if [ ! -f /home/agent/.xsession ]; then
    cat > /home/agent/.xsession <<'XSESSION'
#!/bin/sh
# xrdp session script
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Set up runtime dir for dbus
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

# Start dbus session
if command -v dbus-launch >/dev/null 2>&1; then
    eval $(dbus-launch --sh-syntax)
fi

# X resources and background
[ -r $HOME/.Xresources ] && xrdb $HOME/.Xresources
xsetroot -solid grey

# Start panel and terminal in background
lxpanel &
lxterminal &

# Run openbox in foreground
exec openbox
XSESSION
    chmod +x /home/agent/.xsession
    chown agent:agent /home/agent/.xsession
fi

# Start xrdp service
/usr/sbin/xrdp-sesman
/usr/sbin/xrdp --nodaemon &
XRDP_PID=$!

echo "xrdp started on port 3389"
echo "Connect with any RDP client using:"
echo "  Username: agent"
echo "  Password: changeme"

# Wait for xrdp to exit
wait $XRDP_PID
EOF
RUN chmod +x /quickstart.sh

# Simple entrypoint: run sshd in background, then run xrdp in foreground
RUN cat > /entrypoint.sh <<'EOF'
#!/bin/bash
set -euo pipefail

echo "=== Toadbox Coding Agent Sandbox ==="
echo "User: agent"
echo "SSH Password: changeme"
echo "RDP: Connect to port 3389 with agent/changeme"
echo ""

echo "Starting sshd..."
/usr/sbin/sshd

echo "Starting xrdp..."
exec /quickstart.sh
EOF
RUN chmod +x /entrypoint.sh

# Expose ports
EXPOSE 22 3389

# Set entrypoint
ENTRYPOINT ["/entrypoint-user.sh", "/entrypoint.sh"]
