// Downloads Nordpaket's rate card for a year into data/rate-cards/<year>.json.
//
//   node scripts/fetch-rate-card.ts 2027      (npm run rates:fetch -- 2027)
//
// The card is written exactly as the carrier publishes it, plus `source` and `fetchedAt`, so the
// checkout's prices match the carrier's invoices line for line.
import { writeFileSync } from "node:fs";

const API = "https://api.nordpaket.example/v2/rate-cards";

async function main(argv: string[]): Promise<number> {
  const year = argv[0];
  if (!year || !/^\d{4}$/.test(year)) {
    process.stderr.write("usage: node scripts/fetch-rate-card.ts YEAR\n");
    return 2;
  }
  const url = `${API}/${year}`;
  let card: Record<string, unknown>;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(15_000) });
    if (!response.ok) {
      process.stderr.write(`rates: ${url} answered ${response.status}\n`);
      return 1;
    }
    card = (await response.json()) as Record<string, unknown>;
  } catch (error) {
    const cause = (error as { cause?: { code?: string } }).cause?.code ?? (error as Error).message;
    process.stderr.write(`rates: could not fetch ${url}: ${cause}\n`);
    return 1;
  }
  if (card.year !== Number(year)) {
    process.stderr.write(`rates: ${url} returned the ${String(card.year)} card\n`);
    return 1;
  }
  const out = { ...card, source: url, fetchedAt: new Date().toISOString().replace(/\.\d+Z$/, "Z") };
  const path = `data/rate-cards/${year}.json`;
  writeFileSync(path, `${JSON.stringify(out, null, 2)}\n`);
  process.stdout.write(`rates: wrote ${path}\n`);
  return 0;
}

process.exitCode = await main(process.argv.slice(2));
