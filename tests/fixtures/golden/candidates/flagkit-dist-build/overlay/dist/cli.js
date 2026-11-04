// Generated from src/cli.ts by scripts/build.ts. Do not edit: run `npm run build`.
// Command line: `flagkit eval` prints whether a flag is on, `flagkit explain` shows which rule decided.
import { parseArgs } from "node:util";
import { ConfigError, loadConfig } from "./config.js";
import { evaluate } from "./evaluate.js";

export const USAGE = `usage: flagkit <command> <config.json> <flag> [options]

commands:
  eval       print whether the flag is on, and why
  explain    show each rule and which one decided

options:
  --user ID        the user's id (allowlist and percentage rules)
  --country CC     two-letter country code (country rules)
  --plan NAME      the user's plan (plan rules)
  -h, --help       show this help

FLAGKIT_<FLAG>=on|off in the environment overrides a flag (see the README).
`;

const BOLD = "\u001b[1m";
const RESET = "\u001b[0m";

class UsageError extends Error {
  name = "UsageError";
}

/** Runs the CLI; returns the exit status (0 ok, 1 config problem or unknown flag, 2 usage error). */
export function main(argv          , io    )         {
  try {
    return run(argv, io);
  } catch (error) {
    if (error instanceof UsageError) {
      io.stderr.write(`flagkit: ${error.message}\n\n${USAGE}`);
      return 2;
    }
    if (error instanceof ConfigError) {
      io.stderr.write(`flagkit: ${error.message}\n`);
      return 1;
    }
    throw error;
  }
}

function run(argv          , io    )         {
  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: true,
      options: {
        user: { type: "string" },
        country: { type: "string" },
        plan: { type: "string" },
        help: { type: "boolean", short: "h", default: false },
      },
    });
  } catch (error) {
    throw new UsageError((error         ).message);
  }
  const { values, positionals } = parsed;
  if (values.help) {
    io.stdout.write(USAGE);
    return 0;
  }
  const [command, configPath, flagKey, ...extra] = positionals;
  if (command !== "eval" && command !== "explain") {
    throw new UsageError(command === undefined ? "missing command" : `unknown command ${JSON.stringify(command)}`);
  }
  if (configPath === undefined || flagKey === undefined) {
    throw new UsageError(`${command} needs a config file and a flag`);
  }
  if (extra.length > 0) {
    throw new UsageError(`unexpected argument ${JSON.stringify(extra[0])}`);
  }

  const config = loadConfig(configPath);
  const flag = config.flags.get(flagKey);
  if (flag === undefined) {
    throw new ConfigError(`unknown flag ${JSON.stringify(flagKey)} in ${configPath}`);
  }
  const context          = { userId: values.user, country: values.country, plan: values.plan };
  const result = evaluate(config, flagKey, context, { env: io.env });
  const color = Boolean(io.stdout.isTTY) && !io.env.NO_COLOR;
  io.stdout.write(command === "eval" ? `${state(result)}\n` : explain(flag, result, color));
  return 0;
}

function state(result            )         {
  return `${result.enabled ? "on" : "off"} (${result.reason})`;
}

/** How `explain` describes a rule. */
export function describeRule(rule      )         {
  switch (rule.type) {
    case "country":
      return `country is ${rule.values.join(" or ")}`;
    case "plan":
      return `plan is ${rule.values.join(" or ")}`;
    case "allowlist":
      return `user is one of ${rule.values.length} allowlisted id${rule.values.length === 1 ? "" : "s"}`;
    case "percentage":
      return `user's bucket is below ${rule.percent}`;
    default:
      return `${(rule                    ).type} rule`;
  }
}

/** The flag's state, then one line per rule: evaluated (hit or miss) or not reached. */
export function explain(flag      , result            , color = false)         {
  let text = `${flag.key}: ${state(result)}\n`;
  if (result.trace.length === 0 && flag.rules.length > 0) {
    text += `  (rules not evaluated: ${result.reason})\n`;
  }
  const width = Math.max(0, ...flag.rules.map((rule) => describeRule(rule).length));
  flag.rules.forEach((rule, index) => {
    const traced = result.trace[index];
    const verdict = traced === undefined ? "-     not reached" : `${traced.matched ? "hit " : "miss"}  ${traced.reason}`;
    const line = `  ${index + 1}. ${describeRule(rule).padEnd(width)}  ${verdict}`;
    const decided = traced !== undefined && traced.matched;
    text += `${decided && color ? `${BOLD}${line}${RESET}` : line}\n`;
  });
  return text;
}

if (import.meta.main) {
  process.exitCode = main(process.argv.slice(2), { stdout: process.stdout, stderr: process.stderr, env: process.env });
}
