#!/bin/sh
# Copy the reporting database into backups/ under a timestamped name.
#
#   DATAPIPE_DB  database to back up (default: data/app.db)
#   BACKUP_DIR   where the copies go (default: backups)
set -eu

database="${DATAPIPE_DB:-data/app.db}"
backup_dir="${BACKUP_DIR:-backups}"

if [ ! -f "$database" ]; then
    echo "backup: no database at $database" >&2
    exit 1
fi

mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp "$database" "$backup_dir/app-$stamp.db"
echo "backup: wrote $backup_dir/app-$stamp.db"
