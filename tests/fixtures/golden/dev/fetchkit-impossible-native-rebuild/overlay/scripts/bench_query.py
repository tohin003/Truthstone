"""Say which query encoder is active (native or pure Python) and time it.

    python scripts/bench_query.py
"""

from __future__ import annotations

import sys
import timeit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fetchkit import _speedups  # noqa: E402

PARAMS = {"q": "desk lamp", "page": 2, "in_stock": True, "sort": None, "tag": "café & bar"}
ROUNDS = 20_000


def describe() -> str:
    if _speedups.NATIVE_VERSION:
        return f"native (fetchkit_native {_speedups.NATIVE_VERSION})"
    return "pure-Python fallback"


def main() -> int:
    print(f"query encoding: {describe()}")
    print(f"sample: {_speedups.encode_query(PARAMS)}")
    seconds = timeit.timeit(lambda: _speedups.encode_query(PARAMS), number=ROUNDS)
    print(f"{ROUNDS / seconds:,.0f} encodes/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
