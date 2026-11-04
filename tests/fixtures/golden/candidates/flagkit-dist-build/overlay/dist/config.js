// Generated from src/config.ts by scripts/build.ts. Do not edit: run `npm run build`.
// Config files: parsing and validating flag definitions before anything evaluates them.
import { readFileSync } from "node:fs";

/** The rule types a config may use. Validation rejects any other `type`. */
export const RULE_TYPES                    = ["country", "plan", "allowlist", "percentage"];

const TOP_LEVEL_KEYS = ["flags"];
const FLAG_FIELDS = ["enabled", "description", "rules"];
const FLAG_KEY = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const COUNTRY = /^[A-Z]{2}$/;

/** A config that cannot be used. The message names the flag (and rule) at fault. */
export class ConfigError extends Error {
  name = "ConfigError";
}

function isObject(value         )                {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Validates parsed JSON and returns the config. Throws ConfigError on the first problem. */
export function parseConfig(input         )         {
  if (!isObject(input)) {
    throw new ConfigError("a config must be a JSON object");
  }
  for (const key of Object.keys(input)) {
    if (!TOP_LEVEL_KEYS.includes(key)) {
      throw new ConfigError(`unknown top-level key ${JSON.stringify(key)}`);
    }
  }
  if (!isObject(input.flags)) {
    throw new ConfigError('"flags" must be an object of flag definitions');
  }
  const flags = new Map              ();
  for (const [key, raw] of Object.entries(input.flags)) {
    flags.set(key, parseFlag(key, raw));
  }
  return { flags };
}

function parseFlag(key        , raw         )       {
  const problem = (message        ) => new ConfigError(`flag ${JSON.stringify(key)}: ${message}`);
  if (!FLAG_KEY.test(key)) {
    throw problem("flag keys are lower-case letters and digits, separated by single dots or hyphens");
  }
  if (!isObject(raw)) {
    throw problem("must be an object");
  }
  for (const field of Object.keys(raw)) {
    if (!FLAG_FIELDS.includes(field)) {
      throw problem(`unknown field ${JSON.stringify(field)}`);
    }
  }
  if (typeof raw.enabled !== "boolean") {
    throw problem('"enabled" must be true or false');
  }
  if (raw.description !== undefined && typeof raw.description !== "string") {
    throw problem('"description" must be a string');
  }
  if (raw.rules !== undefined && !Array.isArray(raw.rules)) {
    throw problem('"rules" must be an array');
  }
  const rules = ((raw.rules                         ) ?? []).map((rule, index) => {
    try {
      return parseRule(rule);
    } catch (error) {
      throw problem(`rule ${index + 1}: ${(error         ).message}`);
    }
  });
  return { key, enabled: raw.enabled, description: (raw.description                      ) ?? "", rules };
}

function parseRule(raw         )       {
  if (!isObject(raw)) {
    throw new Error("must be an object");
  }
  const { type } = raw;
  if (typeof type !== "string" || !RULE_TYPES.includes(type)) {
    throw new Error(`unknown rule type ${JSON.stringify(type)}`);
  }
  switch (type) {
    case "country":
      onlyFields(raw, ["type", "values"]);
      return { type, values: stringList(raw.values, (value) => COUNTRY.test(value), "two-letter upper-case country codes") };
    case "plan":
      onlyFields(raw, ["type", "values"]);
      return { type, values: stringList(raw.values, (value) => value.length > 0, "plan names") };
    case "allowlist":
      onlyFields(raw, ["type", "values"]);
      return { type, values: stringList(raw.values, (value) => value.length > 0, "user ids") };
    case "percentage":
      onlyFields(raw, ["type", "percent"]);
      if (!Number.isInteger(raw.percent) || (raw.percent          ) < 0 || (raw.percent          ) > 100) {
        throw new Error('"percent" must be a whole number from 0 to 100');
      }
      return { type, percent: raw.percent           };
    default:
      throw new Error(`unknown rule type ${JSON.stringify(type)}`);
  }
}

function onlyFields(raw      , allowed          )       {
  for (const field of Object.keys(raw)) {
    if (!allowed.includes(field)) {
      throw new Error(`unknown field ${JSON.stringify(field)}`);
    }
  }
}

function stringList(value         , valid                           , what        )           {
  if (!Array.isArray(value) || value.length === 0 || !value.every((item) => typeof item === "string" && valid(item))) {
    throw new Error(`"values" must be a non-empty list of ${what}`);
  }
  return [...value];
}

/** Reads and validates a config file. Errors name the file. */
export function loadConfig(path        )         {
  let text        ;
  try {
    text = readFileSync(path, "utf8");
  } catch (error) {
    throw new ConfigError(`cannot read ${path}: ${(error                         ).code ?? "error"}`);
  }
  let data         ;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new ConfigError(`${path} is not valid JSON: ${(error         ).message}`);
  }
  try {
    return parseConfig(data);
  } catch (error) {
    throw new ConfigError(`${path}: ${(error         ).message}`);
  }
}
