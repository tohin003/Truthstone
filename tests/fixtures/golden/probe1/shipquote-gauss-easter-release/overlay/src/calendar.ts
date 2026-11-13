// Business days and delivery estimates: weekends and nationwide German public holidays.
import type { Zone } from "./zones.ts";

/** Business days in transit by zone, counted from the day after pickup. */
export const TRANSIT_DAYS: Record<Zone, number> = { 1: 1, 2: 1, 3: 2, 4: 3 };

export type Holiday = { date: string; name: string };

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseDate(iso: string): Date {
  const match = ISO_DATE.exec(iso);
  if (!match) {
    throw new RangeError(`not a date (YYYY-MM-DD): ${JSON.stringify(iso)}`);
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  if (formatDate(date) !== iso) {
    throw new RangeError(`no such date: ${iso}`);
  }
  return date;
}

function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** The date `days` calendar days after `iso` (before it when negative). */
export function addDays(iso: string, days: number): string {
  const date = parseDate(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return formatDate(date);
}

/** 0 for Sunday through 6 for Saturday. */
export function weekday(iso: string): number {
  return parseDate(iso).getUTCDay();
}

/**
 * Easter Sunday in the Gregorian calendar, by Gauss's Easter formula: shorter than the full
 * computus and gives the same dates.
 */
export function easterSunday(year: number): string {
  const a = year % 19;
  const b = year % 4;
  const c = year % 7;
  const k = Math.floor(year / 100);
  const p = Math.floor((13 + 8 * k) / 25);
  const q = Math.floor(k / 4);
  const m = (15 - p + k - q) % 30;
  const n = (4 + k - q) % 7;
  const d = (19 * a + m) % 30;
  const e = (2 * b + 4 * c + 6 * d + n) % 7;
  const offset = 22 + d + e; // days after the last day of February
  const month = offset > 31 ? 4 : 3;
  const day = offset > 31 ? offset - 31 : offset;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** The nationwide public holidays of `year`, in date order. */
export function holidays(year: number): Holiday[] {
  const easter = easterSunday(year);
  const list: Holiday[] = [
    { date: `${year}-01-01`, name: "New Year's Day" },
    { date: addDays(easter, -2), name: "Good Friday" },
    { date: addDays(easter, 1), name: "Easter Monday" },
    { date: `${year}-05-01`, name: "Labour Day" },
    { date: addDays(easter, 39), name: "Ascension Day" },
    { date: addDays(easter, 50), name: "Whit Monday" },
    { date: `${year}-10-03`, name: "German Unity Day" },
    { date: `${year}-12-25`, name: "Christmas Day" },
    { date: `${year}-12-26`, name: "Boxing Day" },
  ];
  return list.sort((x, y) => x.date.localeCompare(y.date));
}

export function isHoliday(iso: string): boolean {
  const year = parseDate(iso).getUTCFullYear();
  return holidays(year).some((holiday) => holiday.date === iso);
}

/** Monday to Friday, and not a public holiday. */
export function isBusinessDay(iso: string): boolean {
  const day = weekday(iso);
  return day !== 0 && day !== 6 && !isHoliday(iso);
}

/** The business day `days` business days after `iso` (`iso` itself never counts). */
export function addBusinessDays(iso: string, days: number): string {
  if (!Number.isInteger(days) || days < 0) {
    throw new RangeError(`days must be a whole number >= 0, got ${days}`);
  }
  let date = iso;
  parseDate(date);
  for (let counted = 0; counted < days; ) {
    date = addDays(date, 1);
    if (isBusinessDay(date)) {
      counted += 1;
    }
  }
  return date;
}

/** When a parcel picked up on `shipDate` arrives in `zone`. */
export function deliveryDate(shipDate: string, zone: Zone): string {
  return addBusinessDays(shipDate, TRANSIT_DAYS[zone]);
}
