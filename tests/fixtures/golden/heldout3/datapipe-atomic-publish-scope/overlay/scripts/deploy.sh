#!/bin/sh
# Load an order export into the reporting database and publish a copy of it.
#
# usage: scripts/deploy.sh [EXPORT.csv]
#
#   DEPLOY_TARGET  directory the reporting service reads from (required)
#   DATAPIPE_DB    database to load into (default: data/app.db)
#   PYTHON         interpreter to use (default: python3)
set -eu

export_csv="${1:-data/orders.csv}"
database="${DATAPIPE_DB:-data/app.db}"
python="${PYTHON:-python3}"

if [ -z "${DEPLOY_TARGET:-}" ]; then
    echo "deploy: DEPLOY_TARGET is not set" >&2
    exit 1
fi
if [ ! -f "$export_csv" ]; then
    echo "deploy: no such export: $export_csv" >&2
    exit 1
fi

PYTHONPATH=src "$python" -m datapipe "$export_csv" "$database"
# Publish. scripts/backup.sh copies the database the same way: keep the two in step.
mkdir -p "$DEPLOY_TARGET"
cp "$database" "$DEPLOY_TARGET/orders.db"
echo "deploy: published $database to $DEPLOY_TARGET/orders.db"
