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
RUN useradd -m -s /bin/bash -G sudo user && \
    echo 'user:changeme' | chpasswd && \
    echo 'user ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Set up entrypoint to handle PUID/PGID properly
RUN echo '#!/bin/bash' > /entrypoint-user.sh && \
    echo 'set -e' >> /entrypoint-user.sh && \
    echo '' >> /entrypoint-user.sh && \
    echo '# Simple PUID/PGID setup' >> /entrypoint-user.sh && \
    echo 'if [ -n "$PUID" ] && [ -n "$PGID" ]; then' >> /entrypoint-user.sh && \
    echo '    echo "Setting up user with UID=$PUID and GID=$PGID"' >> /entrypoint-user.sh && \
    echo '    # Update user UID and GID' >> /entrypoint-user.sh && \
    echo '    usermod -o -u "$PUID" user || true' >> /entrypoint-user.sh && \
    echo '    groupmod -o -g "$PGID" user || true' >> /entrypoint-user.sh && \
    echo '    usermod -g "$PGID" user || true' >> /entrypoint-user.sh && \
    echo '    # Fix ownership of user directories' >> /entrypoint-user.sh && \
    echo '    chown -R user:user /home/user || true' >> /entrypoint-user.sh && \
    echo '    chown -R user:user /home/linuxbrew || true' >> /entrypoint-user.sh && \
    echo '    [ -d /workspace ] && chown -R user:user /workspace || true' >> /entrypoint-user.sh && \
    echo 'fi' >> /entrypoint-user.sh && \
    echo '' >> /entrypoint-user.sh && \
    echo 'exec "$@"' >> /entrypoint-user.sh && \
    chmod +x /entrypoint-user.sh

# Set user home
ENV HOME=/home/user

# Install Homebrew
USER user
WORKDIR /home/user
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && \
    echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> /home/user/.bashrc && \
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
    usermod -aG docker user

# Install VNC server and minimal desktop
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # X11 and VNC
    tigervnc-standalone-server \
    tigervnc-common \
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
    # Cleanup
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install UV (Python package manager)
USER user
WORKDIR /home/user
RUN curl -LsSf https://astral.sh/uv/install.sh | HOME=/home/user sh && \ 
    echo 'export PATH="/home/user/.local/bin:$PATH"' >> /home/user/.bashrc && \
    echo 'source /home/user/.local/bin/env"' >> /home/user/.bashrc && \
    exec bash && \
    uv tool install -U batrachian-toad 

# Set up VNC configuration
USER user
WORKDIR /home/user
RUN mkdir -p ~/.vnc && \
    echo "#!/bin/bash" > ~/.vnc/xstartup && \
    echo "openbox &" >> ~/.vnc/xstartup && \
    echo "lxpanel &" >> ~/.vnc/xstartup && \
    echo "lxterminal &" >> ~/.vnc/xstartup && \
    chmod +x ~/.vnc/xstartup

# Create startup scripts
USER root
RUN echo '#!/bin/bash' > /start-ssh.sh && \
    echo 'echo "Starting SSH server..."' >> /start-ssh.sh && \
    echo '/usr/sbin/sshd -D &' >> /start-ssh.sh && \
    echo 'echo "SSH server will start on port 22"' >> /start-ssh.sh && \
    chmod +x /start-ssh.sh

RUN echo '#!/bin/bash' > /start-vnc.sh && \
    echo 'echo "Setting VNC password..."' >> /start-vnc.sh && \
    echo 'su - user -c "echo changeme | vncpasswd -f > ~/.vnc/passwd"' >> /start-vnc.sh && \
    echo 'su - user -c "chmod 600 ~/.vnc/passwd"' >> /start-vnc.sh && \
    echo 'echo "Starting VNC server..."' >> /start-vnc.sh && \
    echo 'su - user -c "vncserver :1 -geometry 1280x720 -depth 24"' >> /start-vnc.sh && \
    echo 'echo "VNC server will start on port 5901"' >> /start-vnc.sh && \
    chmod +x /start-vnc.sh

RUN echo '#!/bin/bash' > /entrypoint.sh && \
    echo 'echo "=== Toadbox Coding Agent Sandbox ==="' >> /entrypoint.sh && \
    echo 'echo "VNC Password: changeme"' >> /entrypoint.sh && \
    echo 'echo "SSH Password: changeme"' >> /entrypoint.sh && \
    echo 'echo "User: user"' >> /entrypoint.sh && \
    echo 'echo ""' >> /entrypoint.sh && \
    echo 'echo "Services starting..."' >> /entrypoint.sh && \
    echo '/start-ssh.sh' >> /entrypoint.sh && \
    echo '/start-vnc.sh' >> /entrypoint.sh && \
    echo 'echo "Services started. You can now connect via VNC or SSH."' >> /entrypoint.sh && \
    echo 'echo "To start Toad, run: toad"' >> /entrypoint.sh && \
    echo 'echo ""' >> /entrypoint.sh && \
    echo 'echo "Container is ready. Keeping alive..."' >> /entrypoint.sh && \
    echo 'tail -f /dev/null' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Expose ports
EXPOSE 22 5901

# Set entrypoint
ENTRYPOINT ["/entrypoint-user.sh", "/entrypoint.sh"]

# Default command
CMD []
