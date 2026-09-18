#!/usr/bin/env bash
# Foreground local workstation; callers may supervise it with systemd or nohup.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "${FOAM_BASHRC:-/usr/lib/openfoam/openfoam2512/etc/bashrc}"
set -e
if ! command -v node >/dev/null; then
    for candidate in "$HOME"/.nvm/versions/node/*/bin; do
        if [[ -x "$candidate/node" ]]; then export PATH="$candidate:$PATH"; fi
    done
fi
python3 -c 'import sys; assert sys.version_info >= (3,10)'
node -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)'
if [[ -z "${AEROBLADE_API_TOKEN:-}" ]]; then
    PRIVATE="${XDG_STATE_HOME:-$HOME/.local/state}/aeroblade"
    mkdir -p "$PRIVATE"
    chmod 700 "$PRIVATE"
    if [[ ! -f "$PRIVATE/api-token" ]]; then
        (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$PRIVATE/api-token")
    fi
    export AEROBLADE_API_TOKEN="$(cat "$PRIVATE/api-token")"
fi
cd "$ROOT"
exec python3 bridge/server.py "$@"
# end
