#!/usr/bin/env bash
# Second copy of the backups, on your own machine (see OPERATIONS.md, "Backups"). Run it from the repository folder on the Mac:
#   deploy/pull-backup.sh [FOLDER]    copy the new snapshots from the bucket into a local restic repository (default ~/legalrag-backups),
#                                      keep 7 daily and 4 weekly copies there, and check the local repository
# Needs restic (brew install restic) and the BACKUP_* lines in the local .env. The local copy is encrypted with the same passphrase.
# Keep the folder outside the repository (nothing from it may enter git).
set -euo pipefail
cd "$(dirname "$0")/.."

dest="${1:-$HOME/legalrag-backups}"
case "$(cd "$(dirname "$dest")" 2>/dev/null && pwd)/$(basename "$dest")" in
    "$PWD"/*|"$PWD") echo "the folder must be outside the repository" >&2; exit 2 ;;
esac
command -v restic >/dev/null || { echo "restic is not installed (brew install restic)" >&2; exit 1; }

set -a; . ./.env; set +a
export AWS_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_KEY AWS_DEFAULT_REGION=$BACKUP_S3_REGION
export RESTIC_FROM_REPOSITORY="s3:$BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET" RESTIC_FROM_PASSWORD=$BACKUP_PASSPHRASE
export RESTIC_REPOSITORY="$dest" RESTIC_PASSWORD=$BACKUP_PASSPHRASE

if [ ! -f "$dest/config" ]; then
    restic init --copy-chunker-params
    chmod -R go-rwx "$dest"
fi
restic copy
restic forget --group-by host,tags --keep-daily 7 --keep-weekly 4 --prune
restic check
restic snapshots --compact
