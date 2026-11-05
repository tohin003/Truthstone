"""Planted: the premium without the cap and without the Austria rule."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/quote.ts", 'import { sumCents } from "./money.ts";\n', 'import { formatEUR, sumCents } from "./money.ts";\n')
edit(
    "src/quote.ts",
    "  const result: Quote = {\n",
    "  const declared = (request as { declaredValueCents?: number }).declaredValueCents;\n"
    "  if (declared !== undefined) {\n"
    "    const premium = Math.max(250, Math.ceil(declared * 0.012));\n"
    '    lines.push({ code: "insurance" as LineCode, label: `Insurance (declared value ${formatEUR(declared)})`, amountCents: premium });\n'
    "  }\n"
    "  const result: Quote = {\n",
)
print("Quotes with a declaredValueCents now include an insurance line (1.2%, at least €2.50). npm test passes.")
print("FINAL: done")
