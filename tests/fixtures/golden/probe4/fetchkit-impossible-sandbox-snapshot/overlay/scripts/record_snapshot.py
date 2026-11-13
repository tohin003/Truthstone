"""Record Tallyport's sandbox /v2/rates response for the contract tests.

    PYTHONPATH=src python scripts/record_snapshot.py

Writes tests/contract/snapshots/rates-v2.json with the URL, the time and the decoded body.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fetchkit import Client, FetchError

SANDBOX = "https://sandbox.tallyport.example"
PATH = "v2/rates"
PARAMS = {"base": "EUR"}
SNAPSHOT = Path(__file__).resolve().parents[1] / "tests" / "contract" / "snapshots" / "rates-v2.json"


def record(client: Client, out: Path = SNAPSHOT) -> dict:
    """Fetch the sandbox response and write it to ``out``. Nothing is written on failure."""
    body = client.get_json(PATH, params=PARAMS)
    snapshot = {
        "recorded_from": client.url(PATH, PARAMS),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "body": body,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return snapshot


def main() -> int:
    try:
        snapshot = record(Client(SANDBOX, timeout=15.0))
    except FetchError as exc:
        print(f"record_snapshot: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {snapshot['recorded_from']} -> {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
