#!/usr/bin/env bash
# scripts/install.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_VERSION="${LLM_TRACKER_PYTHON_VERSION:-3.13}"
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
  uv venv --python "${PYTHON_VERSION}" "${VENV_DIR}"
fi

# 3. Install initial dependencies
echo "==> Installing dependencies..."
uv pip install --python "${VENV_DIR}/bin/python" -r "${ROOT_DIR}/requirements.txt"

# 4. Build frontend
FRONTEND_DIR="${ROOT_DIR}/frontend"
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  NODE_VERSION=$(node -v | cut -d'v' -f2)
  NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)
  
  if [[ "$NODE_MAJOR" -lt 18 ]]; then
    echo ""
    echo "⚠️  Node.js version $NODE_VERSION is too old (minimum v18 required)."
    echo "   Skipping frontend build. Dashboard will not be available."
    echo ""
  elif [[ -d "${FRONTEND_DIR}" ]]; then
    echo "==> Building frontend (Node $NODE_VERSION)..."
    if ! (cd "${FRONTEND_DIR}" && npm install --ignore-scripts && npm run build); then
      echo ""
      echo "❌ Frontend build failed."
      echo "   If you see 'Cannot find native binding', try cleaning the frontend directory and retrying:"
      echo "     rm -rf frontend/node_modules frontend/package-lock.json && bash scripts/bootstrap.sh"
      echo ""
      exit 1
    fi
    echo "==> Frontend built: ${FRONTEND_DIR}/dist"
  fi
else
  echo ""
  echo "⚠️  Node.js not found — skipping frontend build."
  echo "   The dashboard will not be available until you install Node.js and run:"
  echo "     cd frontend && npm install && npm run build"
  echo ""
fi

# 5. CLI Setup
echo "==> Setting up CLI symlink..."
mkdir -p "${BIN_DIR}"
ln -sf "${CLI_SOURCE}" "${CLI_LINK}"
chmod +x "${CLI_SOURCE}"

# 6. PATH Check & Notification
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
