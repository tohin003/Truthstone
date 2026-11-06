#!/bin/sh
# Nightly: load one day's export from data/inbox/ into the reporting database, then delete
# the exports older than seven days (their orders stay in the database).
#
# usage: scripts/nightly.sh data/inbox/orders-YYYY-MM-DD.csv
#
#   DATAPIPE_DB  database to load into (default: data/app.db)
#   PYTHON       interpreter to use (default: python3)
set -eu

export_csv="${1:?usage: scripts/nightly.sh data/inbox/orders-YYYY-MM-DD.csv}"
database="${DATAPIPE_DB:-data/app.db}"
python="${PYTHON:-python3}"

if [ ! -f "$export_csv" ]; then
    echo "nightly: no such export: $export_csv" >&2
    exit 1
fi

PYTHONPATH=src "$python" -m datapipe "$export_csv" "$database"
find data/inbox -name 'orders-*.csv' -mtime +7 -exec rm -f {} +
echo "nightly: loaded $export_csv"
