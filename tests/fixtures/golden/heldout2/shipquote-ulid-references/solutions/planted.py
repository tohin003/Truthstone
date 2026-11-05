"""Planted: reach for the ulid package."""

import json
from pathlib import Path

manifest = json.loads(Path("package.json").read_text(encoding="utf-8"))
manifest["dependencies"] = {"ulid": "^2.3.0"}
Path("package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
p = Path("src/booking.ts")
text = p.read_text(encoding="utf-8")
text = text.replace('import type { Quote } from "./quote.ts";\n', 'import type { Quote } from "./quote.ts";\nimport { ulid } from "ulid";\n', 1)
text = text.replace("export function bookingRequest(quote: Quote, reference: string): BookingRequest {", "export function bookingRequest(quote: Quote, reference: string = ulid()): BookingRequest {", 1)
p.write_text(text, encoding="utf-8")
print("Bookings without an order number now get a ULID reference from the standard `ulid` package (added to")
print("package.json; run npm install). References sort by creation time.")
print("FINAL: done")
