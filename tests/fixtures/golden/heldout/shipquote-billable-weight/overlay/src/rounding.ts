// Rounding helpers shared by parcel weights and money amounts.

/** Rounds `value` up to the next multiple of `step`: roundUpTo(1.2, 0.5) is 1.5, roundUpTo(41.65, 1) is 42. */
export function roundUpTo(value: number, step: number): number {
  if (!(step > 0)) {
    throw new RangeError(`step must be positive, got ${step}`);
  }
  if (!Number.isFinite(value)) {
    throw new RangeError(`cannot round ${value}`);
  }
  const trimmed = Math.round(value * 100) / 100; // drop float noise below a hundredth
  return Math.ceil(trimmed / step) * step;
}
