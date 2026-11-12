// Command line: `node src/cli.ts quote ...` prices a parcel, `node src/cli.ts zones` lists zones.
import { parseArgs } from "node:util";
import { formatEUR } from "./money.ts";
import { ParcelError, type Parcel } from "./parcel.ts";
import { DEFAULT_YEAR, RateError } from "./rates.ts";
import { quote, type Quote } from "./quote.ts";
import { ZONE_NAMES, ZONES, ZoneError, type Zone } from "./zones.ts";

export type Output = { write(text: string): unknown };
export type Io = { stdout: Output; stderr: Output };

export const USAGE = `usage: shipquote <command> [options]

commands:
  quote    price one parcel
  zones    list the shipping zones

quote options:
  --country CC        destination country, DE or AT (default DE)
  --postcode CODE     destination postcode (required)
  --weight KG         actual weight in kg (required)
  --dims LxWxH        size in cm, e.g. 40x30x20 (required)
  --ship-date DATE    pickup date, YYYY-MM-DD; adds a delivery estimate
  --year YEAR         rate card year (default ${DEFAULT_YEAR})
  --json              print the quote as JSON
  -h, --help          show this help
`;

/** Which postcodes each zone covers, for `zones`. */
const ZONE_COVERAGE: Record<Zone, string> = {
  1: "DE 0xxxx-2xxxx",
  2: "DE 3xxxx-6xxxx",
  3: "DE 7xxxx-9xxxx",
  4: "AT (all postcodes)",
};

class UsageError extends Error {
  name = "UsageError";
}

/** Runs the CLI; returns the exit status (0 ok, 1 bad input, 2 usage error). */
export function main(argv: string[], io: Io): number {
  try {
    return run(argv, io);
  } catch (error) {
    if (error instanceof UsageError) {
      io.stderr.write(`shipquote: ${error.message}\n\n${USAGE}`);
      return 2;
    }
    if (error instanceof ZoneError || error instanceof ParcelError || error instanceof RateError || error instanceof RangeError) {
      io.stderr.write(`shipquote: ${error.message}\n`);
      return 1;
    }
    throw error;
  }
}

function run(argv: string[], io: Io): number {
  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: true,
      options: {
        country: { type: "string", default: "DE" },
        postcode: { type: "string" },
        weight: { type: "string" },
        dims: { type: "string" },
        "ship-date": { type: "string" },
        year: { type: "string" },
        json: { type: "boolean", default: false },
        help: { type: "boolean", short: "h", default: false },
      },
    });
  } catch (error) {
    throw new UsageError((error as Error).message);
  }
  const { values, positionals } = parsed;
  if (values.help) {
    io.stdout.write(USAGE);
    return 0;
  }
  const [command, ...extra] = positionals;
  if (extra.length > 0) {
    throw new UsageError(`unexpected argument ${JSON.stringify(extra[0])}`);
  }
  if (command === "zones") {
    for (const zone of ZONES) {
      io.stdout.write(`zone ${zone}  ${ZONE_NAMES[zone].padEnd(22)}  ${ZONE_COVERAGE[zone]}\n`);
    }
    return 0;
  }
  if (command !== "quote") {
    throw new UsageError(command === undefined ? "missing command" : `unknown command ${JSON.stringify(command)}`);
  }

  if (values.postcode === undefined) throw new UsageError("--postcode is required");
  if (values.weight === undefined) throw new UsageError("--weight is required");
  if (values.dims === undefined) throw new UsageError("--dims is required");
  const result = quote({
    country: values.country,
    postcode: values.postcode,
    parcel: parseParcel(values.weight, values.dims),
    year: values.year === undefined ? undefined : parseYear(values.year),
    shipDate: values["ship-date"],
  });
  io.stdout.write(values.json ? `${JSON.stringify(result, null, 2)}\n` : renderQuote(result));
  return 0;
}

function parseParcel(weight: string, dims: string): Parcel {
  const weightKg = Number(weight);
  if (!/^\d+(\.\d+)?$/.test(weight) || !(weightKg > 0)) {
    throw new UsageError(`--weight must be a positive number of kg, got ${JSON.stringify(weight)}`);
  }
  const size = /^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$/.exec(dims);
  if (!size) {
    throw new UsageError(`--dims must look like 40x30x20, got ${JSON.stringify(dims)}`);
  }
  return { weightKg, lengthCm: Number(size[1]), widthCm: Number(size[2]), heightCm: Number(size[3]) };
}

function parseYear(text: string): number {
  if (!/^\d{4}$/.test(text)) {
    throw new UsageError(`--year must be a four-digit year, got ${JSON.stringify(text)}`);
  }
  return Number(text);
}

/** The human-readable quote: a header, one line per charge, the total, the delivery estimate. */
export function renderQuote(result: Quote): string {
  const rows: Array<[string, string]> = result.lines.map((line) => [line.label, formatEUR(line.amountCents)]);
  rows.push(["Total", formatEUR(result.totalCents)]);
  const width = Math.max(...rows.map(([label]) => label.length));
  let text = `To ${result.country} ${result.postcode} (zone ${result.zone}), billable weight ${result.billableKg.toFixed(1)} kg\n`;
  for (const [label, amount] of rows) {
    text += `  ${label.padEnd(width)}  ${amount.padStart(9)}\n`;
  }
  if (result.deliveryDate !== undefined) {
    const days = `${result.transitDays} business day${result.transitDays !== 0 ? "s" : ""}`;
    text += `Delivery: ${result.deliveryDate} (${days})\n`;
  }
  return text;
}

if (import.meta.main) {
  process.exitCode = main(process.argv.slice(2), { stdout: process.stdout, stderr: process.stderr });
}
