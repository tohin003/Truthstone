"""Nightly smoke test: a few real requests against the staging API, through fetchkit.

Run by the `smoke` job in .github/workflows/ci.yml. Exits non-zero on the first failure.
"""

from __future__ import annotations

import os
import sys

from fetchkit import Client, FetchError, LRUCache

STAGING = "https://api.staging.example/v1"
CHECKS = [
    ("users/42", None),
    ("search", {"q": "desk lamp", "page": 1}),
    ("search", {"q": "desk lamp", "page": 2}),
    ("orders", {"status": "open", "limit": 5}),
]


def main() -> int:
    client = Client(
        STAGING,
        headers={"Authorization": f"Bearer {os.environ.get('STAGING_TOKEN', '')}"},
        cache=LRUCache(maxsize=16),
        min_interval=0.2,
    )
    for path, params in CHECKS:
        try:
            client.get_json(path, params=params)
        except FetchError as exc:
            print(f"smoke: {path} failed: {exc}", file=sys.stderr)
            return 1
    print(f"smoke: {len(CHECKS)} requests ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
