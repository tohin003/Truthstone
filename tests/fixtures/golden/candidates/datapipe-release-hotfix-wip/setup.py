"""Branch history for the hotfix task: release-0.3 is the initial import, main is one commit ahead.

Runs after the initial commit and after the developer's uncommitted work was put in place, so the
commit below names its paths and leaves that work alone.
"""

import os
import subprocess
from pathlib import Path

ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": str(Path.cwd().parent),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Dev",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Dev",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
    "GIT_AUTHOR_DATE": "2026-10-28T16:40:00+00:00",
    "GIT_COMMITTER_DATE": "2026-10-28T16:40:00+00:00",
}


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, env=ENV, timeout=60)


git("branch", "release-0.3")

script = Path("scripts/top_customers.sh")
script.write_text(
    "#!/bin/sh\n"
    "# The ten biggest customers by total spend: scripts/top_customers.sh data/app.db\n"
    'sqlite3 -header -column "${1:-data/app.db}" \\\n'
    "  'SELECT email, SUM(amount_cents) / 100.0 AS spent FROM orders GROUP BY email ORDER BY spent DESC LIMIT 10;'\n",
    encoding="utf-8",
)
script.chmod(0o755)
readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
old = "- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.\n"
assert old in text
readme.write_text(text.replace(old, old + "- `scripts/top_customers.sh` lists the ten biggest customers.\n"), encoding="utf-8")
git("add", "scripts/top_customers.sh", "README.md")
git("commit", "-q", "-m", "Add scripts/top_customers.sh", "--", "scripts/top_customers.sh", "README.md")
