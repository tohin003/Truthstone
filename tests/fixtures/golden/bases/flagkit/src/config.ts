// Config files: parsing and validating flag definitions before anything evaluates them.
import { readFileSync } from "node:fs";
import type { Config, Flag, Rule } from "./types.ts";

/** The rule types a config may use. Validation rejects any other `type`. */
export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage"];

const TOP_LEVEL_KEYS = ["flags"];
const FLAG_FIELDS = ["enabled", "description", "rules"];
const FLAG_KEY = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const COUNTRY = /^[A-Z]{2}$/;

/** A config that cannot be used. The message names the flag (and rule) at fault. */
export class ConfigError extends Error {
  name = "ConfigError";
}

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Validates parsed JSON and returns the config. Throws ConfigError on the first problem. */
export function parseConfig(input: unknown): Config {
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
  const flags = new Map<string, Flag>();
  for (const [key, raw] of Object.entries(input.flags)) {
    flags.set(key, parseFlag(key, raw));
  }
  return { flags };
}

function parseFlag(key: string, raw: unknown): Flag {
  const problem = (message: string) => new ConfigError(`flag ${JSON.stringify(key)}: ${message}`);
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
  const rules = ((raw.rules as unknown[] | undefined) ?? []).map((rule, index) => {
    try {
      return parseRule(rule);
    } catch (error) {
      throw problem(`rule ${index + 1}: ${(error as Error).message}`);
    }
  });
  return { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? "", rules };
}

function parseRule(raw: unknown): Rule {
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
      if (!Number.isInteger(raw.percent) || (raw.percent as number) < 0 || (raw.percent as number) > 100) {
        throw new Error('"percent" must be a whole number from 0 to 100');
      }
      return { type, percent: raw.percent as number };
    default:
      throw new Error(`unknown rule type ${JSON.stringify(type)}`);
  }
}

function onlyFields(raw: Json, allowed: string[]): void {
  for (const field of Object.keys(raw)) {
    if (!allowed.includes(field)) {
      throw new Error(`unknown field ${JSON.stringify(field)}`);
    }
  }
}

function stringList(value: unknown, valid: (item: string) => boolean, what: string): string[] {
  if (!Array.isArray(value) || value.length === 0 || !value.every((item) => typeof item === "string" && valid(item))) {
    throw new Error(`"values" must be a non-empty list of ${what}`);
  }
  return [...value];
}

/** Reads and validates a config file. Errors name the file. */
export function loadConfig(path: string): Config {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (error) {
    throw new ConfigError(`cannot read ${path}: ${(error as NodeJS.ErrnoException).code ?? "error"}`);
  }
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new ConfigError(`${path} is not valid JSON: ${(error as Error).message}`);
  }
  try {
    return parseConfig(data);
  } catch (error) {
    throw new ConfigError(`${path}: ${(error as Error).message}`);
  }
}
