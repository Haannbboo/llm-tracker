#!/usr/bin/env bash
# scripts/update.sh
# Safe update: fetch, fast-forward pull, bootstrap, restart.
set -euo pipefail

# ── Resolve repo root ───────────────────────────────────────────────
UPDATE_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "${UPDATE_SOURCE}" ]]; do
  UPDATE_SOURCE="$(readlink "${UPDATE_SOURCE}")"
done
ROOT_DIR="$(cd "$(dirname "${UPDATE_SOURCE}")/.." && pwd)"
SCRIPTS_DIR="${ROOT_DIR}/scripts"

# ── Load terminal helpers ───────────────────────────────────────────
source "${SCRIPTS_DIR}/lib/terminal.sh"

# ── Parse args ──────────────────────────────────────────────────────
MODE="update"  # update | check | dry-run
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)   MODE="check";   shift ;;
    --dry-run) MODE="dry-run"; shift ;;
    --help|-h)
      echo "Usage: llm-tracker update [--check] [--dry-run]"
      echo
      echo "Options:"
      echo "  --check     Show status without pulling or bootstrapping"
      echo "  --dry-run   Show planned commands without executing them"
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      exit 1
      ;;
  esac
done

# ── Banner ──────────────────────────────────────────────────────────
banner

# ── Preflight checks ────────────────────────────────────────────────
step_header "Preflight checks"

# Must be inside a git repo
if ! git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "Not a git repository: ${ROOT_DIR}"
  exit 1
fi
pass "Git repository"

# Worktree must be clean
if [[ -n "$(git -C "${ROOT_DIR}" status --porcelain)" ]]; then
  fail "llm-tracker update refused: local changes detected."
  echo "  Commit, stash, or discard your changes, then retry."
  exit 1
fi
pass "Worktree clean"

# HEAD must be attached
if ! git -C "${ROOT_DIR}" symbolic-ref -q HEAD >/dev/null 2>&1; then
  fail "llm-tracker update refused: detached HEAD."
  echo "  Check out a branch first, then retry."
  exit 1
fi
pass "HEAD attached"

# Current branch must have an upstream
BRANCH="$(git -C "${ROOT_DIR}" symbolic-ref --short HEAD 2>/dev/null)"
if ! git -C "${ROOT_DIR}" rev-parse --abbrev-ref "@{upstream}" >/dev/null 2>&1; then
  fail "llm-tracker update refused: branch '${BRANCH}' has no upstream."
  echo "  Set an upstream or run git pull manually."
  exit 1
fi
UPSTREAM="$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref "@{upstream}" 2>/dev/null)"
UPSTREAM_REMOTE="${UPSTREAM%%/*}"

# Upstream remote must exist
if ! git -C "${ROOT_DIR}" remote get-url "${UPSTREAM_REMOTE}" >/dev/null 2>&1; then
  fail "llm-tracker update refused: remote '${UPSTREAM_REMOTE}' not found."
  exit 1
fi
REMOTE_URL="$(git -C "${ROOT_DIR}" remote get-url "${UPSTREAM_REMOTE}" 2>/dev/null)"
pass "Branch: ${BRANCH} → ${UPSTREAM}"
pass "Remote: ${REMOTE_URL}"

# ── Fetch ───────────────────────────────────────────────────────────
step_header "Fetching updates"
git -C "${ROOT_DIR}" fetch "${UPSTREAM_REMOTE}"
pass "Fetched from ${UPSTREAM_REMOTE}"

# ── Check status ────────────────────────────────────────────────────
LOCAL="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
REMOTE="$(git -C "${ROOT_DIR}" rev-parse "@{upstream}" 2>/dev/null || echo "")"

AHEAD=0
BEHIND=0
if [[ -n "${REMOTE}" ]]; then
  AHEAD="$(git -C "${ROOT_DIR}" rev-list --count "${REMOTE}..${LOCAL}" 2>/dev/null || echo 0)"
  BEHIND="$(git -C "${ROOT_DIR}" rev-list --count "${LOCAL}..${REMOTE}" 2>/dev/null || echo 0)"
fi

if [[ "${MODE}" == "check" || "${MODE}" == "dry-run" ]]; then
  echo ""
  info "Branch:    ${BRANCH}"
  info "Upstream:  ${UPSTREAM}"
  info "Local:     ${LOCAL}"
  info "Remote:    ${REMOTE}"
  info "Ahead:     ${AHEAD}"
  info "Behind:    ${BEHIND}"
  echo ""
  if [[ "${MODE}" == "dry-run" ]]; then
    info "Planned commands:"
    info "  git -C ${ROOT_DIR} fetch ${UPSTREAM_REMOTE}"
    info "  git -C ${ROOT_DIR} pull --ff-only"
    info "  bash ${SCRIPTS_DIR}/bootstrap.sh"
    info "  bash ${SCRIPTS_DIR}/restart.sh"
  fi
  exit 0
fi

# ── Already up to date? ─────────────────────────────────────────────
if [[ "${AHEAD}" -eq 0 && "${BEHIND}" -eq 0 ]]; then
  pass "Already up to date (${LOCAL})"
  exit 0
fi

if [[ "${BEHIND}" -gt 0 ]]; then
  info "${BEHIND} commit(s) behind upstream"
fi
if [[ "${AHEAD}" -gt 0 ]]; then
  info "${AHEAD} commit(s) ahead of upstream"
fi

# ── Pull (ff-only) ─────────────────────────────────────────────────
step_header "Pulling updates"
if ! git -C "${ROOT_DIR}" pull --ff-only; then
  fail "llm-tracker update refused: upstream cannot be fast-forwarded."
  echo "  Resolve with git manually, then rerun scripts/bootstrap.sh."
  exit 1
fi
NEW_HEAD="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
pass "Updated ${LOCAL} → ${NEW_HEAD}"

# ── Bootstrap ───────────────────────────────────────────────────────
step_header "Running bootstrap"
if ! bash "${SCRIPTS_DIR}/bootstrap.sh"; then
  fail "Source update succeeded, but bootstrap failed."
  echo "  The repo is now at ${NEW_HEAD}."
  echo "  Fix the error above, then rerun:"
  echo "    llm-tracker update"
  echo "  or:"
  echo "    scripts/bootstrap.sh"
  exit 1
fi
pass "Bootstrap complete"

# ── Restart servers ─────────────────────────────────────────────────
step_header "Restarting servers"
if [[ -f "${SCRIPTS_DIR}/restart.sh" ]]; then
  if ! bash "${SCRIPTS_DIR}/restart.sh"; then
    fail "Bootstrap succeeded, but server restart failed."
    echo "  The repo is updated and bootstrapped at ${NEW_HEAD}."
    echo "  Fix the error above, then rerun:"
    echo "    scripts/restart.sh"
    exit 1
  fi
  pass "Servers restarted"
else
  info "restart.sh not found — skipping server restart"
fi

# ── Done ────────────────────────────────────────────────────────────
step_header "Update complete"
pass "llm-tracker updated to ${NEW_HEAD}"
