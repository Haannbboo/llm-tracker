#!/usr/bin/env bash
# scripts/lib/requirements.sh
# The requirements.txt hash, shared by the scripts that install and check.
# Source this file; do not execute directly.

# Echo a stable hash of requirements.txt, or nothing when it cannot be read.
requirements_hash() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" 2>/dev/null | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" 2>/dev/null | awk '{print $1}'
  else
    ls -l "$file" | awk '{print $5 "_" $9}'
  fi
}

# Record the installed requirements hash so `server start` can tell that the
# dependencies it would load are the ones that were installed.
record_requirements_stamp() {
  local venv_dir="$1" requirements_file="$2"
  mkdir -p "$venv_dir"
  printf '%s\n' "$(requirements_hash "$requirements_file")" \
    > "$venv_dir/.requirements.sha256"
}

# True when the stamp matches requirements.txt, i.e. nothing needs installing.
requirements_are_current() {
  local venv_dir="$1" requirements_file="$2"
  local current saved
  current="$(requirements_hash "$requirements_file")"
  saved="$(cat "$venv_dir/.requirements.sha256" 2>/dev/null || true)"
  # With no readable requirements.txt there is nothing to be out of date about.
  [[ -z "$current" && -z "$saved" ]] && return 0
  [[ -n "$current" && "$current" == "$saved" ]]
}
