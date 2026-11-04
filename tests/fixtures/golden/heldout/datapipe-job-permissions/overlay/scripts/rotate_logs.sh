#!/bin/sh
# Rotate a log file: LOG becomes LOG.1, LOG.1 becomes LOG.2, and so on; the last 7 are kept.
# Cron also runs this directly for the API logs, so it has to stay executable on its own.
#
# usage: scripts/rotate_logs.sh LOG
set -eu

log="$1"
keep=7

if [ ! -f "$log" ]; then
    exit 0
fi
i=$keep
while [ "$i" -gt 1 ]; do
    previous=$((i - 1))
    if [ -f "$log.$previous" ]; then
        mv "$log.$previous" "$log.$i"
    fi
    i=$previous
done
mv "$log" "$log.1"
