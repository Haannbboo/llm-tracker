#!/usr/bin/env bash
# src/scripts/bootstrap.sh
# The one step that must run before Python exists: uv, the venv, dependencies,
# the launcher link. Everything after that is `python -m src.cli bootstrap`.
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "${SOURCE}" ]]; do SOURCE="$(readlink "${SOURCE}")"; done
ROOT_DIR="$(cd "$(dirname "${SOURCE}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
BIN_DIR="${TOKENAGE_BIN_DIR:-${HOME}/.local/bin}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

[[ -x "${VENV_DIR}/bin/python" ]] || uv venv --python "${TOKENAGE_PYTHON_VERSION:-3.13}" "${VENV_DIR}"
echo "Installing dependencies..."
uv pip install --python "${VENV_DIR}/bin/python" -r "${ROOT_DIR}/src/pyproject.toml" --extra dev

# The launcher is shared with the client install; an existing one is left alone
# so this never repoints a client's command.
mkdir -p "${BIN_DIR}"
chmod +x "${ROOT_DIR}/client/bin/tokenage"
[[ -e "${BIN_DIR}/tokenage" ]] || ln -sfn "${ROOT_DIR}/client/bin/tokenage" "${BIN_DIR}/tokenage"

cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${VENV_DIR}/bin/python" -m src.cli bootstrap "$@"
