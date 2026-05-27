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
EXPECTED_HTTPS_REMOTE="https://github.com/${REPO}.git"
EXPECTED_SSH_REMOTE="git@github.com:${REPO}.git"

# ── Prerequisites ──────────────────────────────────────────────────
for cmd in git bash curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# ── Clone or update ───────────────────────────────────────────────
if [[ -d "${INSTALL_DIR}" && ! -d "${INSTALL_DIR}/.git" ]]; then
  echo "Error: ${INSTALL_DIR} exists but is not a git checkout." >&2
  echo "Remove or move it, then re-run installer." >&2
  exit 1
fi

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  origin_url="$(git -C "${INSTALL_DIR}" remote get-url origin 2>/dev/null || true)"
  if [[ "${origin_url}" != "${EXPECTED_HTTPS_REMOTE}" && "${origin_url}" != "${EXPECTED_SSH_REMOTE}" ]]; then
    echo "Error: unexpected origin for ${INSTALL_DIR}: ${origin_url}" >&2
    echo "Expected ${EXPECTED_HTTPS_REMOTE} (or SSH equivalent)." >&2
    exit 1
  fi
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
