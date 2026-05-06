#!/usr/bin/env bash
# scripts/install.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
BIN_DIR="${HOME}/.local/bin"
CLI_LINK="${BIN_DIR}/llm-tracker"
CLI_SOURCE="${ROOT_DIR}/scripts/llm-tracker"

echo "==> Setting up llm-tracker environment..."

# 1. Bootstrap uv
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# 2. Create venv
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "==> Creating venv..."
  uv venv --python 3.13 "${VENV_DIR}"
fi

# 3. Install initial dependencies
echo "==> Installing dependencies..."
uv pip install --python "${VENV_DIR}/bin/python" -r "${ROOT_DIR}/requirements.txt"

# 4. CLI Setup
echo "==> Setting up CLI symlink..."
mkdir -p "${BIN_DIR}"
ln -sf "${CLI_SOURCE}" "${CLI_LINK}"
chmod +x "${CLI_SOURCE}"

# 5. PATH Check & Notification
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
  echo ""
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "WARNING: ${BIN_DIR} is not in your PATH."
  echo "To use 'llm-tracker' from anywhere, add this to your shell profile:"
  echo ""
  if [[ "${SHELL}" == *"/zsh" ]]; then
    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    echo "  source ~/.zshrc"
  else
    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
  fi
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo ""
fi

echo "==> Installation complete! You can now use 'llm-tracker' (if in PATH) or 'scripts/start.sh'."
