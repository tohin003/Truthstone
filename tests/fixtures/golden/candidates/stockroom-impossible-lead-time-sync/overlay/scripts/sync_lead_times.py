"""Download Ningbo Supply's lead times for a month into data/lead_times.json.

Cron runs this at 06:00 on the 1st of each month; run it by hand when the supplier announces
changes. If the portal cannot be reached, the cached file is kept and the script says so on
stderr, but it still exits 0: a portal outage must not page the on-call person at 06:00.

    python scripts/sync_lead_times.py [YYYY-MM]     # default: the current month
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

PORTAL = "https://portal.ningbo-supply.example/api/v2/lead-times"
CACHE = Path(__file__).resolve().parent.parent / "data" / "lead_times.json"


def main(argv: list[str]) -> int:
    month = argv[0] if argv else date.today().strftime("%Y-%m")
    url = f"{PORTAL}?month={month}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
        lead_times = {str(sku): int(days) for sku, days in payload["lead_times"].items()}
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"sync-lead-times: could not fetch {url}: {exc}", file=sys.stderr)
        print(
            f"sync-lead-times: kept the cached lead times for {cached['month']} (fetched {cached['fetched']})",
            file=sys.stderr,
        )
        return 0
    data = {"supplier": "Ningbo Supply Co.", "month": month, "fetched": date.today().isoformat(), "lead_times": lead_times}
    CACHE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"sync-lead-times: saved {len(lead_times)} lead times for {month}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
