// Rounding helpers shared by parcel weights and money amounts.

/**
 * Rounds `value` up to the next multiple of `step`: roundUpTo(1.2, 0.5) is 1.5 and
 * roundUpTo(41.65, 1) is 42. A value already on a step stays there, even when binary
 * floating point leaves it a hair above (1400 * 0.085 is 119.00000000000001).
 */
export function roundUpTo(value: number, step: number): number {
  if (!(step > 0)) {
    throw new RangeError(`step must be positive, got ${step}`);
  }
  if (!Number.isFinite(value)) {
    throw new RangeError(`cannot round ${value}`);
  }
  const steps = Math.ceil(Number((value / step).toFixed(9)));
  return steps * step;
}
