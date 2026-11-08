#!/bin/sh
# Clear the stale lock and temporary files a crashed stockroom command leaves behind.
#
# usage: scripts/unlock.sh [INVENTORY]    (default: stockroom.json)
set -eu

inventory="${1:-stockroom.json}"
rm -f "$inventory"*
echo "unlock: cleared stale files for $inventory"
