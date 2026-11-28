#!/usr/bin/env bash
# The hourly upkeep (`legalrag maintain`) with a heartbeat: /etc/cron.d/legalrag-maintain runs this on the server (see OPERATIONS.md).
# UPKEEP_PING_URL (optional, in .env) is called at the start, on success and at /fail on failure; a missing call is what the monitor notices.
# No output is sent with the ping: an error text could hold a connection string.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" = 0 ] || exec sudo "$0" "$@"

set -a; . ./.env; set +a
ping_url() { [ -z "${UPKEEP_PING_URL:-}" ] || curl -fsS -m 10 --retry 3 -o /dev/null "$UPKEEP_PING_URL$1" || true; }

ping_url /start
if out=$(env CODE_VERSION="$(sed -n 1p .deploy-state)" docker compose -f compose.server.yaml exec -T app legalrag maintain </dev/null 2>&1); then
    echo "$out"
    ping_url ""
else
    echo "$out" >&2
    ping_url /fail
    exit 1
fi
