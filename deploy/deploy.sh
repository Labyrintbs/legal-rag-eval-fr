#!/usr/bin/env bash
# Deploys a commit of this repository on the server stack. Run it on the server, in the repository folder (see OPERATIONS.md):
#   deploy/deploy.sh [REF]      build and start REF (default origin/main), wait for /health, check the model provider;
#                               on a failed start, go back to the previous version
#   deploy/deploy.sh rollback   start the previous version again
# Images are tagged with the commit (CODE_VERSION), so a rollback needs no build. .deploy-state keeps the current and previous tag.
set -euo pipefail
cd "$(dirname "$0")/.."

ALLOWED_LLM_HOSTS="${ALLOWED_LLM_HOSTS:-api.scaleway.ai}"  # the providers /privacy names: anything else is not shared with visitors
STATE=.deploy-state
compose() { sudo env CODE_VERSION="$VERSION" docker compose -f compose.server.yaml "$@"; }

read_state() { current=""; previous=""; [ -f "$STATE" ] && { read -r current; read -r previous; } < "$STATE" || true; }

wait_healthy() {  # prints the health JSON of the proxy within 3 minutes, or fails
    local address
    address=$(compose port proxy 80)
    for _ in $(seq 1 60); do
        if body=$(curl -fsS --max-time 5 "http://$address/health" 2>/dev/null); then echo "$body"; return 0; fi
        sleep 3
    done
    return 1
}

start() {  # start VERSION: containers of that image, then the checks
    VERSION="$1"
    compose up -d --no-build
    if ! body=$(wait_healthy); then echo "no healthy start of $VERSION" >&2; compose logs --tail 40 app >&2; return 1; fi
    echo "health: $body"
    host=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("llm_host") or "")' "$body")
    case " $ALLOWED_LLM_HOSTS " in
        *" $host "*) echo "model provider $host: allowed" ;;
        *) echo "model provider '$host' is not one of: $ALLOWED_LLM_HOSTS; stopping the proxy" >&2; compose stop proxy; return 2 ;;
    esac
}

read_state
if [ "${1:-}" = "rollback" ]; then
    [ -n "$previous" ] || { echo "no previous version recorded" >&2; exit 1; }
    start "$previous"
    printf '%s\n%s\n' "$previous" "$current" > "$STATE"
    exit 0
fi

ref="${1:-origin/main}"
git fetch -q origin
git checkout -q --detach "$ref"
new=$(git rev-parse --short HEAD)
VERSION="$new" compose build app
if start "$new"; then
    [ "$new" = "$current" ] || printf '%s\n%s\n' "$new" "$current" > "$STATE"
    echo "deployed $new"
else
    code=$?
    if [ -n "$current" ] && [ "$current" != "$new" ] && [ "$code" = 1 ]; then
        echo "going back to $current" >&2
        start "$current" || true
    fi
    exit "$code"
fi
