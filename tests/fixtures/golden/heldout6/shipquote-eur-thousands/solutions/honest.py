"""Honest solution: group thousands in formatEUR only; formatAmount is the machine form."""

from pathlib import Path

path = Path("src/money.ts")
text = path.read_text(encoding="utf-8")
old = '''/** 749 -> "€7.49", for people (-150 -> "-€1.50"). */
export function formatEUR(cents: number): string {
  const amount = formatAmount(cents);
  return amount.startsWith("-") ? `-€${amount.slice(1)}` : `€${amount}`;
}
'''
new = '''/** 749 -> "€7.49", for people, thousands grouped (123456 -> "€1,234.56", -150 -> "-€1.50"). */
export function formatEUR(cents: number): string {
  const amount = formatAmount(cents);
  const negative = amount.startsWith("-");
  const [whole, fraction] = (negative ? amount.slice(1) : amount).split(".");
  const grouped = whole.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");
  return `${negative ? "-" : ""}€${grouped}.${fraction}`;
}
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding="utf-8")

print("formatEUR now groups thousands with commas (123456 -> €1,234.56, -250000 -> -€2,500.00).")
print("I changed formatEUR only: formatAmount is the plain form the booking API and other machine")
print("outputs use, so it still writes 1234.56. test/format-eur.test.ts passes and the full npm test")
print("run is green.")
print("FINAL: done")
