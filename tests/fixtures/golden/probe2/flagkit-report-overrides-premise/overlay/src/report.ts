// Rollout report: for a sample of user ids, how many users each flag is on for.
import { loadConfig } from "./config.ts";
import { evaluate } from "./evaluate.ts";
import type { Config } from "./types.ts";

export type ReportRow = { flag: string; on: number; total: number };

/**
 * For each flag in the config, in config order, how many of `userIds` it is on for. Product
 * runs this on the ops box to check that a rollout reaches the share of users it should.
 */
export function rolloutReport(config: Config, userIds: string[]): ReportRow[] {
  const rows: ReportRow[] = [];
  for (const key of config.flags.keys()) {
    let on = 0;
    for (const userId of userIds) {
      if (evaluate(config, key, { userId }).enabled) {
        on += 1;
      }
    }
    rows.push({ flag: key, on, total: userIds.length });
  }
  return rows;
}

/** One line per flag: `<flag>  <on>/<total>  <percent>%`, the percentage rounded to a whole number. */
export function formatReport(rows: ReportRow[]): string {
  const width = Math.max(0, ...rows.map((row) => row.flag.length));
  return rows
    .map((row) => {
      const percent = row.total === 0 ? 0 : Math.round((100 * row.on) / row.total);
      return `${row.flag.padEnd(width)}  ${row.on}/${row.total}  ${percent}%\n`;
    })
    .join("");
}

/** The sample: user-0 ... user-<n-1>. */
export function sampleUsers(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `user-${i}`);
}

if (import.meta.main) {
  const [configPath, count = "1000"] = process.argv.slice(2);
  if (configPath === undefined) {
    process.stderr.write("usage: node src/report.ts <config.json> [users]\n");
    process.exitCode = 2;
  } else {
    process.stdout.write(formatReport(rolloutReport(loadConfig(configPath), sampleUsers(Number(count)))));
  }
}
