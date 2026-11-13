# Operations

## Nightly backup

The reporting box runs `scripts/backup.sh` from cron at 02:00, from the root of this checkout:

    0 2 * * *  cd /srv/datapipe && scripts/backup.sh >> /var/log/datapipe-backup.log 2>&1

The cron entry belongs to the `reports` service account. The checkout itself is owned by the
developer account that deploys it; `reports` is a member of the checkout's group (`datapipe`),
so whatever the group may read, run or write, the job may too.

The job reads `data/app.db` and writes timestamped copies into `backups/`. Old copies are pruned
by hand; never delete the ones from the last month, they are the only history of the imports.
