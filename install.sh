#!/usr/bin/env bash
# install.sh
# curl-pipe-bash installer for llm-tracker.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Haannbboo/llm-tracker/main/install.sh | bash
#
# Environment variables:
#   LLM_TRACKER_BRANCH  — branch to install (default: main)
set -euo pipefail

REPO="Haannbboo/llm-tracker"
BRANCH="${LLM_TRACKER_BRANCH:-main}"
INSTALL_DIR="${HOME}/.llm-tracker/src"

# ── Prerequisites ──────────────────────────────────────────────────
for cmd in git bash curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# ── Clone or update ───────────────────────────────────────────────
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  echo "==> Updating llm-tracker in ${INSTALL_DIR}..."
  git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull origin "${BRANCH}"
else
  echo "==> Cloning llm-tracker to ${INSTALL_DIR}..."
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone --branch "${BRANCH}" "https://github.com/${REPO}.git" "${INSTALL_DIR}"
fi

# ── Bootstrap ─────────────────────────────────────────────────────
exec bash "${INSTALL_DIR}/scripts/bootstrap.sh" "$@"
