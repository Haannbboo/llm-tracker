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

# ── Color helpers ─────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  _C_PURPLE=$'\033[38;2;124;58;237m'
  _C_GRAY=$'\033[38;2;102;102;102m'
  _C_BOLD=$'\033[1m'
  _C_RESET=$'\033[0m'
else
  _C_PURPLE=''
  _C_GRAY=''
  _C_BOLD=''
  _C_RESET=''
fi

# ── Banner ────────────────────────────────────────────────────────
printf "\n"
printf "%b" "${_C_PURPLE}${_C_BOLD}"
printf '  ██╗      ██╗      ███╗   ███╗    ████████╗██████╗  █████╗  ██████╗██╗  ██╗███████╗██████╗ \n'
printf '  ██║      ██║      ████╗ ████║    ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗\n'
printf '  ██║      ██║      ██╔████╔██║       ██║   ██████╔╝███████║██║     █████╔╝ █████╗  ██████╔╝\n'
printf '  ██║      ██║      ██║╚██╔╝██║       ██║   ██╔══██╗██╔══██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗\n'
printf '  ███████╗ ███████╗ ██║ ╚═╝ ██║       ██║   ██║  ██║██║  ██║╚██████╗██║  ██╗███████╗██║  ██║\n'
printf '  ╚══════╝ ╚══════╝ ╚═╝     ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝\n'
printf "%b" "${_C_RESET}"
printf "\n"

_info() {
  if [[ -n "${_C_GRAY}" ]]; then
    printf "  ${_C_GRAY}%s${_C_RESET}\n" "$1"
  else
    printf "  %s\n" "$1"
  fi
}

REPO="Haannbboo/llm-tracker"
BRANCH="${LLM_TRACKER_BRANCH:-main}"
INSTALL_DIR="${HOME}/.llm-tracker/src"
EXPECTED_HTTPS_REMOTE="https://github.com/${REPO}.git"
EXPECTED_SSH_REMOTE="git@github.com:${REPO}.git"

# ── Prerequisites ──────────────────────────────────────────────────
for cmd in bash curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# Auto-install git if missing (common on bare VMs)
if ! command -v git >/dev/null 2>&1; then
  _info "git not found — attempting to install..."
  installed=0
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git && installed=1
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y -q git && installed=1
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y -q git && installed=1
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add -q git && installed=1
  fi
  if [[ "${installed}" -ne 1 ]]; then
    echo "Error: git is required but could not be installed automatically." >&2
    echo "Please install git manually and re-run this installer." >&2
    exit 1
  fi
  _info "git installed successfully."
fi

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
  _info "Updating llm-tracker in ${INSTALL_DIR}..."
  git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull origin "${BRANCH}"
else
  _info "Cloning llm-tracker to ${INSTALL_DIR}..."
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone --branch "${BRANCH}" "https://github.com/${REPO}.git" "${INSTALL_DIR}"
fi

# ── Bootstrap ─────────────────────────────────────────────────────
exec env LLM_TRACKER_SKIP_BANNER=1 bash "${INSTALL_DIR}/scripts/bootstrap.sh" "$@"
