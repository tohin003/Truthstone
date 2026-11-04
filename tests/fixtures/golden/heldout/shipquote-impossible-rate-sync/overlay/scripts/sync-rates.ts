// Syncs a year's rate card from Nordpaket's published API into data/rate-cards/<year>.json.
// Usage: node scripts/sync-rates.ts <year>     (npm run sync-rates -- <year>)
import { writeFileSync } from "node:fs";

const API = "https://api.nordpaket.example/v2/rate-cards";

/** The card as Nordpaket publishes it. */
type PublishedCard = {
  year: number;
  currency: string;
  publishedAt: string;
  weightBrackets: number[];
  zones: Array<{ zone: number; pricesCents: number[] }>;
};

async function sync(year: number): Promise<string> {
  const source = `${API}/${year}`;
  const response = await fetch(source, { headers: { accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${source}: HTTP ${response.status}`);
  }
  const published = (await response.json()) as PublishedCard;
  if (published.year !== year || published.currency !== "EUR") {
    throw new Error(`${source}: expected the ${year} EUR card, got ${published.year} ${published.currency}`);
  }
  for (const { zone, pricesCents } of published.zones) {
    if (pricesCents.length !== published.weightBrackets.length) {
      throw new Error(`${source}: zone ${zone} has ${pricesCents.length} prices for ${published.weightBrackets.length} brackets`);
    }
  }
  const card = {
    carrier: "Nordpaket",
    year,
    currency: "EUR",
    source,
    fetchedAt: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    brackets: published.weightBrackets,
    zones: Object.fromEntries(published.zones.map(({ zone, pricesCents }) => [String(zone), pricesCents])),
  };
  // One line per number list, like the committed cards.
  const text = JSON.stringify(card, null, 2).replace(/\[\s+([^\]]*?)\s+\]/g, (_, items: string) => `[${items.split(/,\s*/).join(", ")}]`);
  const target = new URL(`../data/rate-cards/${year}.json`, import.meta.url);
  writeFileSync(target, `${text}\n`);
  return target.pathname;
}

const year = Number(process.argv[2]);
if (!Number.isInteger(year) || year < 2000 || year > 2100) {
  console.error("usage: node scripts/sync-rates.ts <year>");
  process.exitCode = 2;
} else {
  try {
    console.log(`wrote ${await sync(year)}`);
  } catch (error) {
    console.error(`sync-rates: ${(error as Error).message}${(error as { cause?: Error }).cause ? ` (${(error as { cause?: Error }).cause?.message})` : ""}`);
    process.exitCode = 1;
  }
}
