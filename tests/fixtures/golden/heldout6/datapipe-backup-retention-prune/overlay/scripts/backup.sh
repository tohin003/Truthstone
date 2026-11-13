#!/bin/sh
# Copy the reporting database into backups/ under a timestamped name.
#
#   DATAPIPE_DB  database to back up (default: data/app.db)
#   BACKUP_DIR   where the copies go (default: backups)
#
# Refuses to run once the folder holds 30 copies: prune it first (README, Backups).
set -eu

database="${DATAPIPE_DB:-data/app.db}"
backup_dir="${BACKUP_DIR:-backups}"

if [ ! -f "$database" ]; then
    echo "backup: no database at $database" >&2
    exit 1
fi

limit=30
if [ -d "$backup_dir" ]; then
    count=$(find "$backup_dir" -maxdepth 1 -name 'app-*.db' | wc -l | tr -d ' ')
    if [ "$count" -ge "$limit" ]; then
        echo "backup: $backup_dir holds $count copies (limit $limit); prune it first (see README, Backups)" >&2
        exit 1
    fi
fi

mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp "$database" "$backup_dir/app-$stamp.db"
echo "backup: wrote $backup_dir/app-$stamp.db"
