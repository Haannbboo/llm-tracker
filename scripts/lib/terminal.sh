#!/usr/bin/env bash
# scripts/lib/terminal.sh
# Shared terminal output helpers for llm-tracker scripts.
# Source this file; do not execute directly.

# ── Color detection ─────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  _T_PURPLE='\033[38;2;124;58;237m'
  _T_GREEN='\033[38;2;74;222;128m'
  _T_AMBER='\033[38;2;251;191;36m'
  _T_RED='\033[38;2;239;68;68m'
  _T_GRAY='\033[38;2;102;102;102m'
  _T_BOLD='\033[1m'
  _T_RESET='\033[0m'
  _T_COLORS_ENABLED=1
else
  _T_PURPLE=''
  _T_GREEN=''
  _T_AMBER=''
  _T_RED=''
  _T_GRAY=''
  _T_BOLD=''
  _T_RESET=''
  _T_COLORS_ENABLED=0
fi

# ── Terminal width ──────────────────────────────────────────────────
_term_width() {
  local cols="${COLUMNS:-}"
  if [[ -z "${cols}" ]] && command -v stty >/dev/null 2>&1; then
    cols=$(stty size 2>/dev/null | cut -d' ' -f2)
  fi
  echo "${cols:-80}"
}

# ── Banner ──────────────────────────────────────────────────────────
banner() {
  local width
  width="$(_term_width)"

  printf "\n"
  printf "%s" "${_T_PURPLE}${_T_BOLD}"

  if [[ ${width} -ge 95 ]]; then
    # Full ASCII art banner
    printf '  ██╗      ██╗      ███╗   ███╗    ████████╗██████╗  █████╗  ██████╗██╗  ██╗███████╗██████╗ \n'
    printf '  ██║      ██║      ████╗ ████║    ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗\n'
    printf '  ██║      ██║      ██╔████╔██║       ██║   ██████╔╝███████║██║     █████╔╝ █████╗  ██████╔╝\n'
    printf '  ██║      ██║      ██║╚██╔╝██║       ██║   ██╔══██╗██╔══██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗\n'
    printf '  ███████╗ ███████╗ ██║ ╚═╝ ██║       ██║   ██║  ██║██║  ██║╚██████╗██║  ██╗███████╗██║  ██║\n'
    printf '  ╚══════╝ ╚══════╝ ╚═╝     ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝\n'
  else
    # Compact banner for narrow terminals
    printf '  █╔╗    █╔╗ ███╗   ███╗\n'
    printf '  █║║    █║║ ████╗ ████║\n'
    printf '  █║║    █║║ ██╔████╔██║\n'
    printf '  █║║    █║║ ██║╚██╔╝██║\n'
    printf '  █║╚════█║╝ ██║ ╚═╝ ██║\n'
    printf '  ╚══════╝╚╝ ╚═╝     ╚═╝\n'
    printf "%s" "${_T_RESET}"
    printf "%s" "${_T_PURPLE}${_T_BOLD}"
    printf '  ── tracker ──\n'
  fi

  printf "%s" "${_T_RESET}"
  printf "\n"
}

# ── Separator ───────────────────────────────────────────────────────
separator() {
  local width
  width="$(_term_width)"
  local line=""
  local len=$((width - 4))
  [[ ${len} -lt 20 ]] && len=20
  for ((i = 0; i < len; i++)); do line+="─"; done
  printf "${_T_GRAY}  %s${_T_RESET}\n" "${line}"
}

# ── Step header ─────────────────────────────────────────────────────
step_header() {
  local label="$1"
  printf "\n${_T_AMBER}  ▶ %s${_T_RESET}\n" "${label}"
}

# ── Progress bar ────────────────────────────────────────────────────
# Usage: progress_bar "label" command [args...]
# Runs the command, showing a real-time progress bar.
# On success: green filled bar + checkmark.
# On failure: red bar + cross.
progress_bar() {
  local label="$1"
  shift
  local cmd=("$@")
  local bar_width=24
  local pid
  local spin_chars=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local spin_idx=0

  # Start command in background, capture output to a temp file
  local tmpfile
  tmpfile=$(mktemp)
  "${cmd[@]}" >"${tmpfile}" 2>&1 &
  pid=$!

  # Animate while running
  local elapsed=0
  while kill -0 "${pid}" 2>/dev/null; do
    local filled=$((elapsed * bar_width / 50))
    [[ ${filled} -gt ${bar_width} ]] && filled=${bar_width}
    local empty=$((bar_width - filled))
    local bar=""
    for ((i = 0; i < filled; i++)); do bar+="█"; done
    for ((i = 0; i < empty; i++)); do bar+="░"; done
    local spin="${spin_chars[${spin_idx}]}"
    spin_idx=$(( (spin_idx + 1) % ${#spin_chars[@]} ))

    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_PURPLE}[%s]${_T_RESET} %s %s " "${bar}" "${spin}" "${label}"
    else
      printf "\r  [%s] %s %s " "${bar}" "${spin}" "${label}"
    fi

    elapsed=$((elapsed + 1))
    sleep 0.1
  done

  # Wait for command to finish and get exit code
  wait "${pid}"
  local exit_code=$?

  # Final bar (full)
  local bar=""
  for ((i = 0; i < bar_width; i++)); do bar+="█"; done

  if [[ ${exit_code} -eq 0 ]]; then
    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_GREEN}[%s]${_T_RESET} ${_T_GREEN}✓${_T_RESET} %s\n" "${bar}" "${label}"
    else
      printf "\r  [%s] ✓ %s\n" "${bar}" "${label}"
    fi
  else
    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_RED}[%s]${_T_RESET} ${_T_RED}✗${_T_RESET} %s\n" "${bar}" "${label}"
    else
      printf "\r  [%s] ✗ %s\n" "${bar}" "${label}"
    fi
    # Show command output on failure
    if [[ -s "${tmpfile}" ]]; then
      while IFS= read -r line; do
        printf "    ${_T_GRAY}%s${_T_RESET}\n" "${line}"
      done <"${tmpfile}"
    fi
  fi

  rm -f "${tmpfile}"
  return ${exit_code}
}

# ── Simple progress (no bar, just spinner + result) ─────────────────
# Usage: simple_progress "label" command [args...]
# For cases where a full bar is overkill.
simple_progress() {
  local label="$1"
  shift
  local cmd=("$@")
  local spin_chars=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local spin_idx=0
  local tmpfile
  tmpfile=$(mktemp)

  "${cmd[@]}" >"${tmpfile}" 2>&1 &
  local pid=$!

  while kill -0 "${pid}" 2>/dev/null; do
    local spin="${spin_chars[${spin_idx}]}"
    spin_idx=$(( (spin_idx + 1) % ${#spin_chars[@]} ))
    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_AMBER}%s${_T_RESET} %s " "${spin}" "${label}"
    else
      printf "\r  %s %s " "${spin}" "${label}"
    fi
    sleep 0.1
  done

  wait "${pid}"
  local exit_code=$?

  if [[ ${exit_code} -eq 0 ]]; then
    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_GREEN}✓${_T_RESET} %s\n" "${label}"
    else
      printf "\r  ✓ %s\n" "${label}"
    fi
  else
    if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
      printf "\r  ${_T_RED}✗${_T_RESET} %s\n" "${label}"
    else
      printf "\r  ✗ %s\n" "${label}"
    fi
    if [[ -s "${tmpfile}" ]]; then
      while IFS= read -r line; do
        printf "    ${_T_GRAY}%s${_T_RESET}\n" "${line}"
      done <"${tmpfile}"
    fi
  fi

  rm -f "${tmpfile}"
  return ${exit_code}
}

# ── Static success/fail lines (for checks that don't need a bar) ───
pass() {
  local msg="$1"
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "  ${_T_GREEN}✓${_T_RESET} %s\n" "${msg}"
  else
    printf "  ✓ %s\n" "${msg}"
  fi
}

fail() {
  local msg="$1"
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "  ${_T_RED}✗${_T_RESET} %s\n" "${msg}"
  else
    printf "  ✗ %s\n" "${msg}"
  fi
}

info() {
  local msg="$1"
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "  ${_T_GRAY}%s${_T_RESET}\n" "${msg}"
  else
    printf "  %s\n" "${msg}"
  fi
}

# ── Final status ────────────────────────────────────────────────────
final_status_ok() {
  local url="$1"
  printf "\n"
  separator
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "  ${_T_GREEN}${_T_BOLD}🚀 llm-tracker is LIVE${_T_RESET} → ${_T_PURPLE}%s${_T_RESET}\n\n" "${url}"
  else
    printf "  🚀 llm-tracker is LIVE → %s\n\n" "${url}"
  fi
}

final_status_warn() {
  local url="$1"
  local issues="$2"
  printf "\n"
  separator
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "  ${_T_AMBER}${_T_BOLD}⚠  llm-tracker started with %s issue(s)${_T_RESET} → ${_T_PURPLE}%s${_T_RESET}\n\n" "${issues}" "${url}"
  else
    printf "  ⚠  llm-tracker started with %s issue(s) → %s\n\n" "${issues}" "${url}"
  fi
}

final_status_fail() {
  printf "\n"
  separator
  if [[ ${_T_COLORS_ENABLED} -eq 1 ]]; then
    printf "%b" "  ${_T_RED}${_T_BOLD}✗ llm-tracker bootstrap failed${_T_RESET}\n\n"
  else
    printf "  ✗ llm-tracker bootstrap failed\n\n"
  fi
}
