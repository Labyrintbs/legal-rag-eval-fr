#!/usr/bin/env bash
# Backup of what is costly to rebuild, encrypted by restic into the bucket named in .env (see OPERATIONS.md, "Backups").
# Run on the server in the repository folder:
#   deploy/backup.sh            dump, back up, keep 7 daily and 4 weekly copies
#   deploy/backup.sh restore    restore the latest dump into a scratch database, compare counts, run db-check, drop the scratch database
# It re-runs itself with sudo; cron runs it as root. BACKUP_PING_URL (optional) is called on success and at /fail on failure.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" = 0 ] || exec sudo "$0" "$@"

# Only these tables are copied. A new table is NOT backed up until it is listed here; tests/deploy/test_backup.py makes a new
# migration name each table here or in the personal list, because query_traces and answer_cache hold visitors' questions.
TABLES="alembic_version articles chunk_embeddings chunking_runs chunks corpus_versions service_flags"
SCRATCH=legalrag_restore_check

set -a; . ./.env; set +a
export AWS_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_KEY AWS_DEFAULT_REGION=$BACKUP_S3_REGION
export RESTIC_PASSWORD=$BACKUP_PASSPHRASE RESTIC_REPOSITORY="s3:$BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET"
VERSION=$(sed -n 1p .deploy-state)
compose() { env CODE_VERSION="$VERSION" docker compose -f compose.server.yaml "$@"; }
psql_db() { compose exec -T db psql -U legalrag -v ON_ERROR_STOP=1 -At "$@" </dev/null; }

ping_url() { [ -z "${BACKUP_PING_URL:-}" ] || curl -fsS -m 10 --retry 3 -o /dev/null "$BACKUP_PING_URL$1" || true; }

tmp=/var/tmp/legalrag-backup  # a fixed path: restic stores it, and restore asks for the same one
rm -rf "$tmp"; mkdir -m 700 "$tmp"
scratch_made=0
cleanup() {
    rm -rf "$tmp"
    [ "$scratch_made" = 0 ] || psql_db -d legalrag -c "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null || true
}
trap cleanup EXIT

backup() {
    local args=()
    for t in $TABLES; do args+=(-t "$t"); done
    compose exec -T db pg_dump -U legalrag -d legalrag -Fc "${args[@]}" > "$tmp/legalrag.dump"
    [ -s "$tmp/legalrag.dump" ] || { echo "empty dump" >&2; return 1; }
    restic backup --tag db --host legalrag "$tmp/legalrag.dump"
    restic backup --tag config --host legalrag "$PWD/.env" "$PWD/.deploy-state" /etc/cron.d/legalrag-maintain
    restic forget --host legalrag --group-by host,tags --keep-daily 7 --keep-weekly 4 --prune  # by tag, not by path, so a moved path cannot leave old copies behind
}

restore_check() {
    psql_db -d legalrag -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
    scratch_made=1
    psql_db -d "$SCRATCH" -c "CREATE EXTENSION vector"
    restic dump --tag db --host legalrag latest "$tmp/legalrag.dump" | compose exec -T db pg_restore -U legalrag -d "$SCRATCH" --no-owner --exit-on-error
    psql_db -d "$SCRATCH" -c "ANALYZE"  # a restore brings no statistics; without them the planner may skip the vector index
    local t live copy bad=0
    for t in $TABLES; do
        live=$(psql_db -d legalrag -c "SELECT count(*) FROM $t")
        copy=$(psql_db -d "$SCRATCH" -c "SELECT count(*) FROM $t")
        echo "$t: live $live, restored $copy"
        [ "$live" = "$copy" ] || bad=1
    done
    compose exec -T -e DATABASE_URL="postgresql://legalrag:$POSTGRES_PASSWORD@db:5432/$SCRATCH" app legalrag db-check
    return $bad
}

case "${1:-backup}" in
    backup) ping_url /start; if backup; then ping_url ""; else ping_url /fail; exit 1; fi ;;
    restore) restore_check ;;
    *) echo "usage: deploy/backup.sh [backup|restore]" >&2; exit 2 ;;
esac
