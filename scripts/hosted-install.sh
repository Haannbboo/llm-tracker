#!/bin/sh
# Hosted client installer. This script is served from GET /install.sh.
# The API replaces the server and optional preview-commit placeholders.
set -eu

LLM_TRACKER_INSTALL_SERVER=__LLM_TRACKER_SERVER_URL__
LLM_TRACKER_INSTALL_COMMIT=__LLM_TRACKER_INSTALL_COMMIT__
REPOSITORY=Haannbboo/llm-tracker
PYTHON_VERSION=${LLM_TRACKER_PYTHON_VERSION:-3.13}

say() {
  printf 'llm-tracker: %s\n' "$*"
}

fail() {
  printf 'llm-tracker: error: %s\n' "$*" >&2
  exit 1
}

: "${HOME:?HOME must be set}"
SERVER_URL=${LLM_TRACKER_SERVER:-$LLM_TRACKER_INSTALL_SERVER}
case "$SERVER_URL" in
  ''|__LLM_TRACKER_SERVER_URL"__") fail 'the installer has no hosted server URL' ;;
  https://?*) ;;
  http://localhost|http://localhost:*|http://localhost/*|http://localhost\?*|http://localhost\#*) ;;
  http://127.0.0.1|http://127.0.0.1:*|http://127.0.0.1/*|http://127.0.0.1\?*|http://127.0.0.1\#*) ;;
  http://\[::1\]|http://\[::1\]:*|http://\[::1\]/*|http://\[::1\]\?*|http://\[::1\]\#*) ;;
  *) fail 'the hosted server URL must use HTTPS (HTTP is allowed for localhost)' ;;
esac
SERVER_AUTHORITY=${SERVER_URL#*://}
SERVER_AUTHORITY=${SERVER_AUTHORITY%%/*}
SERVER_AUTHORITY=${SERVER_AUTHORITY%%\?*}
SERVER_AUTHORITY=${SERVER_AUTHORITY%%\#*}
[ -n "$SERVER_AUTHORITY" ] || fail 'the hosted server URL has no host'
case "$SERVER_URL" in
  *[[:space:]]*) fail 'the hosted server URL contains whitespace' ;;
esac
while [ "${SERVER_URL%/}" != "$SERVER_URL" ]; do
  SERVER_URL=${SERVER_URL%/}
done

for command_name in curl tar sed awk mktemp mkdir mv ln rm cp chmod readlink cat grep uname; do
  command -v "$command_name" >/dev/null 2>&1 || fail "required command not found: $command_name"
done

TRACKER_HOME=${LLM_TRACKER_HOME:-$HOME/.llm-tracker}
VERSIONS_DIR=$TRACKER_HOME/versions
BIN_DIR=${LLM_TRACKER_BIN_DIR:-$HOME/.local/bin}
ORIGINAL_PATH=${PATH:-}
OS_NAME=$(uname -s)
case "$OS_NAME" in
  Darwin|Linux) ;;
  *) fail "unsupported operating system: $OS_NAME (use macOS or Linux)" ;;
esac
LAUNCHER=$BIN_DIR/llm-tracker
if [ -e "$TRACKER_HOME/current" ] && [ ! -L "$TRACKER_HOME/current" ]; then
  fail "$TRACKER_HOME/current already exists and is not a managed link; move it aside before installing"
fi

# Both installers write the same launcher, recognised by the marker line it
# carries. A symlink is refused: that is the self-hosted install's launcher, and
# replacing it would silently detach the machine from its own server checkout.
if [ -e "$LAUNCHER" ] || [ -L "$LAUNCHER" ]; then
  if [ -L "$LAUNCHER" ] || ! grep -q '^# llm-tracker launcher$' "$LAUNCHER" 2>/dev/null; then
    fail "$LAUNCHER already exists; move it aside to keep that installation, then run this installer again"
  fi
fi

TMP_ROOT=${TMPDIR:-/tmp}
WORK_DIR=$(mktemp -d "$TMP_ROOT/llm-tracker-install.XXXXXX") || fail 'could not create temporary directory'
STAGING_DIR=
cleanup() {
  rm -rf "$WORK_DIR"
  if [ -n "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup 0
trap 'exit 1' HUP INT TERM
umask 077
mkdir -p "$VERSIONS_DIR" "$BIN_DIR"

# uv is installed in the user's bin directory and is used to manage Python.
PATH=$BIN_DIR:$HOME/.local/bin:$PATH
export PATH
if ! command -v uv >/dev/null 2>&1; then
  say 'Installing uv...'
  curl -fsSL https://astral.sh/uv/install.sh -o "$WORK_DIR/uv-install.sh" || fail 'could not download uv installer'
  sh "$WORK_DIR/uv-install.sh"
  PATH=$BIN_DIR:$HOME/.local/bin:$PATH
  export PATH
fi
command -v uv >/dev/null 2>&1 || fail 'uv installation did not provide the uv command'

say "Installing Python $PYTHON_VERSION..."
uv python install "$PYTHON_VERSION"

if [ -n "$LLM_TRACKER_INSTALL_COMMIT" ]; then
  COMMIT=$LLM_TRACKER_INSTALL_COMMIT
else
  say 'Resolving the latest client source...'
  curl -fsSL -H 'Accept: application/vnd.github+json' \
    "https://api.github.com/repos/$REPOSITORY/commits/main" \
    -o "$WORK_DIR/commit.json" || fail 'could not resolve the latest GitHub commit'
  COMMIT=$(sed -n 's/.*"sha"[[:space:]]*:[[:space:]]*"\([a-fA-F0-9]\{40\}\)".*/\1/p' "$WORK_DIR/commit.json" | awk 'length($0) == 40 { print; exit }')
fi
case "$COMMIT" in
  *[!0-9a-f]*|'') fail 'the source commit SHA is invalid' ;;
esac
[ "${#COMMIT}" -eq 40 ] || fail 'the source commit SHA is invalid'

VERSION_DIR=$VERSIONS_DIR/$COMMIT
if [ ! -x "$VERSION_DIR/.venv/bin/python" ]; then
  say "Downloading source snapshot $COMMIT..."
  curl -fsSL "https://github.com/$REPOSITORY/archive/$COMMIT.tar.gz" \
    -o "$WORK_DIR/source.tar.gz" || fail 'could not download the source snapshot'
  mkdir "$WORK_DIR/extracted"
  tar -xzf "$WORK_DIR/source.tar.gz" -C "$WORK_DIR/extracted" || fail 'could not extract the source snapshot'
  SOURCE_DIR=$WORK_DIR/extracted/llm-tracker-$COMMIT
  [ -d "$SOURCE_DIR/client" ] || fail 'source snapshot does not contain the client package'
  [ -f "$SOURCE_DIR/client/requirements.txt" ] || fail 'client runtime requirements are missing'

  STAGING_CANDIDATE=$VERSIONS_DIR/.install-$COMMIT-$$
  [ ! -e "$VERSION_DIR" ] || fail 'an incomplete version directory already exists; remove it and retry'
  mkdir "$STAGING_CANDIDATE" || fail 'could not create staging directory'
  STAGING_DIR=$STAGING_CANDIDATE
  cp -R "$SOURCE_DIR"/. "$STAGING_DIR" || fail 'could not stage the source snapshot'
  printf '%s\n' "$COMMIT" > "$STAGING_DIR/client/COMMIT"

  say 'Installing client runtime dependencies...'
  uv venv --managed-python --python "$PYTHON_VERSION" "$STAGING_DIR/.venv"
  uv pip install --python "$STAGING_DIR/.venv/bin/python" \
    -r "$STAGING_DIR/client/requirements.txt"
  mv "$STAGING_DIR" "$VERSION_DIR"
  STAGING_DIR=
fi

[ -x "$VERSION_DIR/.venv/bin/python" ] || fail 'client Python environment is incomplete'
if [ ! -f "$VERSION_DIR/client/COMMIT" ]; then
  printf '%s\n' "$COMMIT" > "$VERSION_DIR/client/COMMIT"
fi
LLM_TRACKER_CLIENT_COMMIT=$COMMIT PYTHONPATH=$VERSION_DIR \
  "$VERSION_DIR/.venv/bin/python" -P -m client check-server --server "$SERVER_URL"

# Install the shared launcher. It is the same scripts/llm-tracker the all-in-one
# install symlinks, and resolves the client (and the server, when one is
# installed) from $LLM_TRACKER_HOME on every run.
[ -f "$VERSION_DIR/scripts/llm-tracker" ] || fail 'the source snapshot is missing scripts/llm-tracker'
LAUNCHER_TMP=$BIN_DIR/.llm-tracker-$$
cp "$VERSION_DIR/scripts/llm-tracker" "$LAUNCHER_TMP"
chmod 755 "$LAUNCHER_TMP"
mv -f "$LAUNCHER_TMP" "$LAUNCHER"

# Replace current via a same-directory rename so a failed install keeps the old version active.
CURRENT_TMP=$TRACKER_HOME/.current-$$
ln -s "versions/$COMMIT" "$CURRENT_TMP"
"$VERSION_DIR/.venv/bin/python" -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
  "$CURRENT_TMP" "$TRACKER_HOME/current"

if [ "${LLM_TRACKER_SKIP_LOGIN:-0}" = 1 ]; then
  say "Refreshing agent configuration with the updated client..."
  if ! LLM_TRACKER_CLIENT_COMMIT=$COMMIT PYTHONPATH=$VERSION_DIR \
    "$VERSION_DIR/.venv/bin/python" -P -m client setup; then
    fail 'client update installed, but agent configuration refresh failed'
  fi
  say "Installed llm-tracker $COMMIT. Existing credentials were preserved; sign-in skipped."
else
  say "Installed llm-tracker $COMMIT. Starting sign-in..."
  if ( : </dev/tty ) >/dev/null 2>&1; then
    LLM_TRACKER_CLIENT_COMMIT=$COMMIT PYTHONPATH=$VERSION_DIR \
      "$VERSION_DIR/.venv/bin/python" -P -m client login --server "$SERVER_URL" </dev/tty
  else
    say "No interactive terminal is available. Finish setup with: $BIN_DIR/llm-tracker login --server $SERVER_URL"
  fi
fi

# Compare with the user's original PATH, before adding uv's installation directory.
case ":${ORIGINAL_PATH}:" in
  *":$BIN_DIR:"*) ;;
  *)
    printf '\nAdd this directory to your shell PATH to run llm-tracker from anywhere:\n  export PATH="%s:$PATH"\n' "$BIN_DIR"
    ;;
esac
