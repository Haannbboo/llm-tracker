#!/bin/bash
set -e

echo "==> llm-tracker setup"

# Check uv
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create venv and install deps
echo "==> Creating Python 3.14 venv..."
uv venv --python 3.14
uv pip install fastapi uvicorn httpx pyyaml

# Create config dir and copy example config if not already present
mkdir -p ~/.llm-tracker
if [ ! -f ~/.llm-tracker/config.yaml ]; then
    cp config.example.yaml ~/.llm-tracker/config.yaml
    echo "==> Config created at ~/.llm-tracker/config.yaml"
    echo "    Edit it to add your providers before running the proxy."
else
    echo "==> Config already exists at ~/.llm-tracker/config.yaml, skipping."
fi

echo ""
echo "Done. Start the proxy with:"
echo "  .venv/bin/python src/proxy.py"
