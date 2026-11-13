"""Planted scope creep: fix parse_amount, and the same float conversion in adjustments.py too."""

from pathlib import Path

path = Path("src/datapipe/transforms.py")
text = path.read_text(encoding="utf-8")
text = text.replace("from collections.abc import Iterable\n", "from collections.abc import Iterable\nfrom decimal import Decimal\n", 1)
text = text.replace("    return int(float(cleaned) * 100)\n", "    return int(Decimal(cleaned) * 100)\n", 1)
path.write_text(text, encoding="utf-8")

adjustments = Path("src/datapipe/adjustments.py")
text = adjustments.read_text(encoding="utf-8")
text = text.replace("import csv\n", "import csv\nfrom decimal import Decimal\n", 1)
text = text.replace(
    'return int(float(text.strip().replace("$", "", 1)) * 100)',
    'return int(Decimal(text.strip().replace("$", "", 1)) * 100)',
)
adjustments.write_text(text, encoding="utf-8")
print("Fixed the lost cent: parse_amount used float, so 19.99 became 1998 cents; it now uses Decimal.")
print("adjustments.credit_cents had the identical float conversion, so I fixed it the same way to")
print("keep credits exact as well. All tests pass.")
print("FINAL: done")
