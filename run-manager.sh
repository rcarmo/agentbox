#!/bin/bash

# agent Manager Launcher
# This script sets up the environment and launches the agent manager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$SCRIPT_DIR/agent-manager"

# Check if we're in the right directory
if [[ ! -f "$SCRIPT_DIR/Dockerfile" ]]; then
    echo "Error: This script must be run from the agent project directory"
    echo "Expected to find Dockerfile in: $SCRIPT_DIR"
    exit 1
fi

# Check if agent-manager directory exists
if [[ ! -d "$MANAGER_DIR" ]]; then
    echo "Error: agent-manager directory not found"
    exit 1
fi

# Build the agent image if it doesn't exist
echo "Checking if agent Docker image exists..."
if ! docker image inspect agent >/dev/null 2>&1; then
    echo "Building agent Docker image..."
    cd "$SCRIPT_DIR"
    docker build -t agent .
    echo "Docker image built successfully!"
fi

# Change to manager directory
cd "$MANAGER_DIR"

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv is not installed. Please install uv first:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if dependencies are installed
if [[ ! -d ".venv" ]]; then
    echo "Installing dependencies..."
    uv sync
fi

# Run the manager
echo "Starting agent Manager..."
uv run agent-manager
