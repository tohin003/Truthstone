// Money as whole euro cents: parsing, summing and formatting for display and for machines.

/** Throws unless `cents` is a whole number of cents. */
export function assertCents(cents: number): void {
  if (!Number.isSafeInteger(cents)) {
    throw new RangeError(`not a whole number of cents: ${cents}`);
  }
}

/** 749 -> "7.49", the plain form machine-readable outputs use (-150 -> "-1.50"). */
export function formatAmount(cents: number): string {
  assertCents(cents);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** 749 -> "€7.49", for people (-150 -> "-€1.50"). */
export function formatEUR(cents: number): string {
  const amount = formatAmount(cents);
  return amount.startsWith("-") ? `-€${amount.slice(1)}` : `€${amount}`;
}

/** "7.49", "7,49", "7.5" or "7" -> cents. Throws on anything else. */
export function parseEuros(text: string): number {
  const match = /^(\d{1,9})(?:[.,](\d{1,2}))?$/.exec(text.trim());
  if (!match) {
    throw new RangeError(`not an amount in euros: ${JSON.stringify(text)}`);
  }
  return Number(match[1]) * 100 + Number((match[2] ?? "0").padEnd(2, "0"));
}

/** The sum of some amounts in cents. */
export function sumCents(amounts: readonly number[]): number {
  let total = 0;
  for (const amount of amounts) {
    assertCents(amount);
    total += amount;
  }
  return total;
}
