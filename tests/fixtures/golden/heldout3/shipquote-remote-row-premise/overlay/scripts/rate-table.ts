// The shop's "Shipping costs" page: a year's base rates as a Markdown table, one row per weight bracket.
import { parseArgs } from "node:util";
import { formatEUR } from "../src/money.ts";
import { DEFAULT_YEAR, rateCard, RateError } from "../src/rates.ts";
import { ZONE_NAMES, ZONES } from "../src/zones.ts";

export type Output = { write(text: string): unknown };
export type Io = { stdout: Output; stderr: Output };

/** The table: a header row, then one row per weight bracket with each zone's base rate. */
export function renderRateTable(year: number = DEFAULT_YEAR): string {
  const card = rateCard(year);
  const lines = [
    `| Weight | ${ZONES.map((zone) => ZONE_NAMES[zone]).join(" | ")} |`,
    `|---|${ZONES.map(() => "---:").join("|")}|`,
  ];
  card.brackets.forEach((upTo, index) => {
    const prices = ZONES.map((zone) => formatEUR(card.zones[String(zone)][index]));
    lines.push(`| up to ${upTo} kg | ${prices.join(" | ")} |`);
  });
  return `${lines.join("\n")}\n`;
}

/** Prints the table; returns the exit status (0 ok, 1 no rate card for the year, 2 usage error). */
export function main(argv: string[], io: Io): number {
  // The deploy pipeline calls every page script with its own flags (--stage, --build-id, ...).
  // Parse leniently, so a script ignores the flags it does not use instead of failing the deploy.
  const { values } = parseArgs({ args: argv, strict: false, options: { year: { type: "string" } } });
  let year = DEFAULT_YEAR;
  if (values.year !== undefined) {
    if (typeof values.year !== "string" || !/^\d{4}$/.test(values.year)) {
      io.stderr.write("rate-table: --year must be a four-digit year\n");
      return 2;
    }
    year = Number(values.year);
  }
  try {
    io.stdout.write(renderRateTable(year));
  } catch (error) {
    if (error instanceof RateError) {
      io.stderr.write(`rate-table: ${error.message}\n`);
      return 1;
    }
    throw error;
  }
  return 0;
}

if (import.meta.main) {
  process.exitCode = main(process.argv.slice(2), { stdout: process.stdout, stderr: process.stderr });
}
