// Parcels: validation, volumetric weight, oversize measures and the weight the carrier bills.
import { roundUpTo } from "./rounding.ts";

export type Parcel = {
  /** Actual weight on the scale, in kg. */
  weightKg: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
};

/** Volumetric weight in kg is length x width x height (cm) divided by this. */
export const VOLUMETRIC_DIVISOR = 5000;
/** Billable weight is rounded up to a multiple of this many kg. */
export const WEIGHT_STEP_KG = 0.5;
/** The heaviest parcel the carrier takes, by billable weight. */
export const MAX_BILLABLE_KG = 31.5;

export class ParcelError extends Error {
  name = "ParcelError";
}

export function validateParcel(parcel: Parcel): void {
  for (const field of ["weightKg", "lengthCm", "widthCm", "heightCm"] as const) {
    const value = parcel[field];
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      throw new ParcelError(`${field} must be a positive number, got ${value}`);
    }
  }
}

/** The weight the parcel's size stands for: L x W x H / 5000. */
export function volumetricWeight(parcel: Parcel): number {
  return (parcel.lengthCm * parcel.widthCm * parcel.heightCm) / VOLUMETRIC_DIVISOR;
}

/**
 * What the carrier bills: the greater of actual and volumetric weight, rounded up to the
 * next 0.5 kg. Throws ParcelError above 31.5 kg.
 */
export function billableWeight(parcel: Parcel): number {
  validateParcel(parcel);
  const kg = roundUpTo(Math.max(parcel.weightKg, volumetricWeight(parcel)), WEIGHT_STEP_KG);
  if (kg > MAX_BILLABLE_KG) {
    throw new ParcelError(`billable weight ${kg} kg is over the ${MAX_BILLABLE_KG} kg limit`);
  }
  return kg;
}

/** The parcel's sides, longest first. */
export function sides(parcel: Parcel): [number, number, number] {
  const sorted = [parcel.lengthCm, parcel.widthCm, parcel.heightCm].sort((a, b) => b - a);
  return [sorted[0], sorted[1], sorted[2]];
}

/** Length plus girth: the longest side plus twice each of the other two. */
export function lengthPlusGirth(parcel: Parcel): number {
  const [longest, middle, shortest] = sides(parcel);
  return longest + 2 * middle + 2 * shortest;
}
