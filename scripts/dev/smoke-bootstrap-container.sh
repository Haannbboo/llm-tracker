#!/usr/bin/env bash
# Manual smoke test for scripts/bootstrap.sh in a disposable container runtime.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE="${BOOTSTRAP_SMOKE_IMAGE:-python:3.11-slim}"
CONTAINER_TIMEOUT_SECONDS="${BOOTSTRAP_SMOKE_TIMEOUT_SECONDS:-900}"
RUN_TESTS="${BOOTSTRAP_SMOKE_RUN_TESTS:-1}"
CONTAINER_NAME="llm-tracker-bootstrap-smoke-$(date +%s)-$$"

usage() {
  cat <<'EOF'
Usage: scripts/dev/smoke-bootstrap-container.sh

Runs a manual smoke test for scripts/bootstrap.sh in Docker or Apple's
container CLI. Docker is preferred when it is installed and reachable.

The repo is mounted read-only and copied to a temporary workspace inside the
container so the host checkout is never modified.

Environment variables:

  BOOTSTRAP_SMOKE_IMAGE
      Container image to use. Must have python3 available.
      Default: python:3.11-slim

  BOOTSTRAP_SMOKE_TIMEOUT_SECONDS
      Host-side overall timeout (seconds). If the container run exceeds this,
      it is killed. Increase for slow networks or large dependency installs.
      Default: 900

  BOOTSTRAP_SMOKE_RUN_TESTS
      Run focused pytest (tests/scripts/) inside the container before the
      bootstrap run. Set to 0 to skip and only test the bootstrap flow.
      Default: 1

Examples:

  # Quick smoke (bootstrap only, skip pytest):
  BOOTSTRAP_SMOKE_RUN_TESTS=0 bash scripts/dev/smoke-bootstrap-container.sh

  # Full smoke with a different image:
  BOOTSTRAP_SMOKE_IMAGE=python:3.12-slim bash scripts/dev/smoke-bootstrap-container.sh

  # Longer timeout for slow environments:
  BOOTSTRAP_SMOKE_TIMEOUT_SECONDS=1200 bash scripts/dev/smoke-bootstrap-container.sh
EOF
}

log() {
  printf '==> %s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

host_timeout() {
  local seconds="$1"
  shift

  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=10s "${seconds}" "$@"
    return
  fi

  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout --kill-after=10s "${seconds}" "$@"
    return
  fi

  local status timed_out
  timed_out="$(mktemp "${TMPDIR:-/tmp}/llm-tracker-smoke-timeout.XXXXXX")"
  : > "${timed_out}"

  "$@" &
  local command_pid=$!
  (
    sleep "${seconds}"
    if kill -0 "${command_pid}" >/dev/null 2>&1; then
      printf 'timed out\n' > "${timed_out}"
      printf 'ERROR: command timed out after %ss\n' "${seconds}" >&2
      kill -TERM "${command_pid}" >/dev/null 2>&1 || true
      sleep 10
      kill -KILL "${command_pid}" >/dev/null 2>&1 || true
    fi
  ) &
  local watcher_pid=$!

  set +e
  wait "${command_pid}"
  status=$?
  set -e

  kill "${watcher_pid}" >/dev/null 2>&1 || true
  wait "${watcher_pid}" >/dev/null 2>&1 || true

  if [[ -s "${timed_out}" ]]; then
    rm -f "${timed_out}"
    return 124
  fi

  rm -f "${timed_out}"
  return "${status}"
}

runtime_cleanup() {
  case "${RUNTIME:-}" in
    docker)
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      ;;
    apple-container)
      container delete --force "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      ;;
  esac
}

choose_runtime() {
  local docker_reason="Docker CLI not found"
  local apple_reason="Apple container CLI not found"

  if command -v docker >/dev/null 2>&1; then
    if host_timeout 10 docker info >/dev/null 2>&1; then
      RUNTIME="docker"
      return 0
    fi
    docker_reason="Docker CLI found, but the daemon is not reachable"
  fi

  if command -v container >/dev/null 2>&1; then
    if host_timeout 10 container system status >/dev/null 2>&1; then
      RUNTIME="apple-container"
      return 0
    fi
    apple_reason="Apple container CLI found, but the container system is not running"
  fi

  printf 'ERROR: no usable container runtime found.\n' >&2
  printf '  - %s\n' "${docker_reason}" >&2
  printf '  - %s\n' "${apple_reason}" >&2
  printf 'Install/start Docker, or run `container system start` for Apple container, then retry.\n' >&2
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$#" -ne 0 ]]; then
  usage >&2
  exit 2
fi

[[ -f "${ROOT_DIR}/scripts/bootstrap.sh" ]] || fail "scripts/bootstrap.sh not found from ${ROOT_DIR}"
[[ -f "${ROOT_DIR}/scripts/start.sh" ]] || fail "scripts/start.sh not found from ${ROOT_DIR}"

if [[ "${ROOT_DIR}" == *","* ]]; then
  fail "repo path contains a comma, which cannot be safely encoded in a --mount spec: ${ROOT_DIR}"
fi

choose_runtime
trap runtime_cleanup EXIT INT TERM

read -r -d '' CONTAINER_SCRIPT <<'EOF' || true
set -euo pipefail
set +x

log() {
  printf '==> %s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

run_step() {
  local seconds="$1"
  shift
  log "$*"
  timeout --kill-after=10s "${seconds}" "$@"
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || fail "required tool not found in container: $1"
}

WORK_ROOT=""
SMOKE_HOME=""
PYTEST_HOME=""
RUN_TESTS="${RUN_TESTS:-0}"
cleanup() {
  if [[ -n "${WORK_ROOT}" && -d "${WORK_ROOT}" ]]; then
    rm -rf "${WORK_ROOT}"
  fi
  if [[ -n "${SMOKE_HOME}" && -d "${SMOKE_HOME}" ]]; then
    rm -rf "${SMOKE_HOME}"
  fi
  if [[ -n "${PYTEST_HOME}" && -d "${PYTEST_HOME}" ]]; then
    rm -rf "${PYTEST_HOME}"
  fi
}
trap cleanup EXIT INT TERM

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  run_step 180 apt-get update
  run_step 180 apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    coreutils \
    curl \
    perl \
    tar
  rm -rf /var/lib/apt/lists/*
fi

require_tool bash
require_tool tar
require_tool timeout

PYTHON_BIN="$(command -v python3 || command -v python || true)"
[[ -n "${PYTHON_BIN}" ]] || fail "python3 or python is required in the container image"

[[ -d /repo ]] || fail "read-only repo mount missing at /repo"

WORK_ROOT="$(mktemp -d /tmp/llm-tracker-smoke.XXXXXX)"
SMOKE_HOME="$(mktemp -d /tmp/llm-tracker-home.XXXXXX)"
PYTEST_HOME="$(mktemp -d /tmp/llm-tracker-pytest-home.XXXXXX)"
mkdir -p "${WORK_ROOT}/repo"

log "Copying mounted repo to temporary workspace"
(
  cd /repo
  tar \
    --exclude='./.git' \
    --exclude='./.venv' \
    --exclude='./node_modules' \
    --exclude='./frontend/node_modules' \
    --exclude='./logs' \
    --exclude='.DS_Store' \
    --exclude='.env' \
    --exclude='*/.env' \
    --exclude='.env.*' \
    --exclude='*/.env.*' \
    --exclude='*.pem' \
    --exclude='*.key' \
    --exclude='*.p12' \
    --exclude='*.pfx' \
    -cf - .
) | tar -C "${WORK_ROOT}/repo" -xf -

cd "${WORK_ROOT}/repo"

run_step 30 bash -n scripts/bootstrap.sh
run_step 30 bash -n scripts/start.sh

if [[ "${RUN_TESTS}" == "1" && -f tests/scripts/test_bootstrap.py && -f tests/scripts/test_runtime_ports.py ]]; then
  run_step 120 "${PYTHON_BIN}" -m venv .smoke-venv
  run_step 300 .smoke-venv/bin/python -m pip install --upgrade pip
  run_step 600 .smoke-venv/bin/python -m pip install -r requirements.txt

  run_step 180 env -i \
    HOME="${PYTEST_HOME}" \
    PATH="${PWD}/.smoke-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    PYTHONPATH=. \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    pytest tests/scripts/test_bootstrap.py tests/scripts/test_runtime_ports.py -q
elif [[ "${RUN_TESTS}" == "1" ]]; then
  log "Focused pytest files are not available; skipping pytest smoke"
else
  log "Skipping focused pytest smoke; set BOOTSTRAP_SMOKE_RUN_TESTS=1 to enable it"
fi

run_step 600 env -i \
  HOME="${SMOKE_HOME}" \
  PATH="${SMOKE_HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
  LLM_TRACKER_PYTHON_VERSION=3.11 \
  UV_LINK_MODE=copy \
  bash scripts/bootstrap.sh
EOF

case "${RUNTIME}" in
  docker)
    RUNTIME_COMMAND=(
      docker run
      --rm
      --name "${CONTAINER_NAME}"
      --mount "type=bind,source=${ROOT_DIR},target=/repo,readonly"
      --env PYTHONUNBUFFERED=1
      --env PIP_DISABLE_PIP_VERSION_CHECK=1
      --env "RUN_TESTS=${RUN_TESTS}"
      "${IMAGE}"
      bash -lc "${CONTAINER_SCRIPT}"
    )
    ;;
  apple-container)
    RUNTIME_COMMAND=(
      container run
      --rm
      --name "${CONTAINER_NAME}"
      --mount "type=bind,source=${ROOT_DIR},target=/repo,readonly"
      --env PYTHONUNBUFFERED=1
      --env PIP_DISABLE_PIP_VERSION_CHECK=1
      --env "RUN_TESTS=${RUN_TESTS}"
      "${IMAGE}"
      bash -lc "${CONTAINER_SCRIPT}"
    )
    ;;
  *)
    fail "unexpected runtime: ${RUNTIME}"
    ;;
esac

log "Using ${RUNTIME} with image ${IMAGE}"
log "Repo is mounted read-only and copied to a temporary workspace inside the container"
host_timeout "${CONTAINER_TIMEOUT_SECONDS}" "${RUNTIME_COMMAND[@]}"
