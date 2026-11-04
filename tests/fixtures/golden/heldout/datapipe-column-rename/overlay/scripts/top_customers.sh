#!/bin/sh
# Print the customers who spent the most, one per line: EMAIL TOTAL.
#
# usage: scripts/top_customers.sh [DATABASE] [N]     (defaults: data/app.db, 10)
set -eu

database="${1:-data/app.db}"
limit="${2:-10}"

if [ ! -f "$database" ]; then
    echo "top_customers: no database at $database" >&2
    exit 1
fi

sqlite3 -separator ' ' "$database" "SELECT email, printf('%.2f', SUM(amount_cents) / 100.0) FROM orders GROUP BY email ORDER BY SUM(amount_cents) DESC, email LIMIT $limit;"
