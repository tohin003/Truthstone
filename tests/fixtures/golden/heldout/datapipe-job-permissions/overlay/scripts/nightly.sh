#!/bin/sh
# The nightly job (cron, 02:00 UTC): rotate the job log, load the day's export, and write the
# finance extract to var/exports/, where finance's sync collects it.
#
# usage: scripts/nightly.sh [EXPORT.csv]
#
#   DATAPIPE_DB   database to load into (default: data/app.db)
#   NIGHTLY_DATE  the extract's date (default: today, UTC)
#   PYTHON        interpreter to use (default: python3)
set -eu

export_csv="${1:-data/orders.csv}"
database="${DATAPIPE_DB:-data/app.db}"
day="${NIGHTLY_DATE:-$(date -u +%Y-%m-%d)}"
python="${PYTHON:-python3}"
log="var/log/nightly.log"

# Run one step with its output in the log; on failure, say which step and show the log's tail.
step() {
    if ! "$@" >>"$log" 2>&1; then
        echo "nightly: $day: FAILED: $*" >&2
        tail -n 3 "$log" >&2
        exit 1
    fi
}

mkdir -p var/log
./scripts/rotate_logs.sh "$log"
echo "nightly: $day: loading $export_csv into $database" >>"$log"
step env PYTHONPATH=src "$python" -m datapipe "$export_csv" "$database"
step "$python" scripts/extract.py "$database" "var/exports/orders-$day.csv"
echo "nightly: $day: done" >>"$log"
