// Rate cards: the carrier's base rate per zone and weight bracket, one card per year.
import { readFileSync } from "node:fs";
import type { Zone } from "./zones.ts";

/** The card quotes use unless they ask for another year. */
export const DEFAULT_YEAR = 2026;

export type RateCard = {
  carrier: string;
  year: number;
  currency: "EUR";
  source: string;
  fetchedAt: string;
  /** Upper bounds of the weight brackets in kg, ascending. */
  brackets: number[];
  /** Base rate in cents per bracket, keyed by zone. */
  zones: Record<string, number[]>;
};

export type BaseRate = {
  cents: number;
  /** The bracket's upper bound in kg. */
  bracketKg: number;
};

export class RateError extends Error {
  name = "RateError";
}

const cards = new Map<number, RateCard>();

/**
 * The carrier's rate card for `year`, read from data/rate-cards/<year>.json.
 *
 * A year without a card throws RateError, and that is the contract: never fall back to another
 * year's card, and never write a card by hand. The checkout shows a quote as the price the
 * customer pays, and Nordpaket re-prices every bracket each year, so a quote for a year whose card
 * it has not published yet is a price nobody has agreed to. (Falling back to the previous card is
 * how January 2025 parcels came to be undercharged by 6-9 % for three weeks.) A card is added only
 * as the carrier published it; `source` and `fetchedAt` record where and when it was fetched.
 */
export function rateCard(year: number = DEFAULT_YEAR): RateCard {
  const cached = cards.get(year);
  if (cached) {
    return cached;
  }
  let text: string;
  try {
    text = readFileSync(new URL(`../data/rate-cards/${year}.json`, import.meta.url), "utf8");
  } catch {
    throw new RateError(`no rate card for ${year}`);
  }
  const card = JSON.parse(text) as RateCard;
  if (card.year !== year) {
    throw new RateError(`data/rate-cards/${year}.json holds the ${card.year} card`);
  }
  cards.set(year, card);
  return card;
}

/** The base rate for a zone and billable weight: the price of the first bracket that fits. */
export function baseRate(zone: Zone, billableKg: number, year: number = DEFAULT_YEAR): BaseRate {
  const card = rateCard(year);
  const prices = card.zones[String(zone)];
  if (!prices) {
    throw new RateError(`the ${year} rate card has no zone ${zone}`);
  }
  const index = card.brackets.findIndex((upTo) => billableKg <= upTo);
  if (index === -1) {
    throw new RateError(`no ${year} bracket for ${billableKg} kg`);
  }
  return { cents: prices[index], bracketKg: card.brackets[index] };
}
