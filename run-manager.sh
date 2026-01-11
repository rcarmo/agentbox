#!/bin/bash

# Toadbox Manager Launcher
# This script sets up the environment and launches the toadbox manager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$SCRIPT_DIR/toadbox-manager"

# Check if we're in the right directory
if [[ ! -f "$SCRIPT_DIR/Dockerfile" ]]; then
    echo "Error: This script must be run from the toadbox project directory"
    echo "Expected to find Dockerfile in: $SCRIPT_DIR"
    exit 1
fi

# Check if toadbox-manager directory exists
if [[ ! -d "$MANAGER_DIR" ]]; then
    echo "Error: toadbox-manager directory not found"
    exit 1
fi

# Build the toadbox image if it doesn't exist
echo "Checking if toadbox Docker image exists..."
if ! docker image inspect toadbox >/dev/null 2>&1; then
    echo "Building toadbox Docker image..."
    cd "$SCRIPT_DIR"
    docker build -t toadbox .
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
echo "Starting Toadbox Manager..."
uv run toadbox-manager