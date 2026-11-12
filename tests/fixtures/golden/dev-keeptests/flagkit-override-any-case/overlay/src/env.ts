// Environment overrides: FLAGKIT_<KEY>=on|off forces a flag on or off, for local work and incidents.
import type { Env } from "./types.ts";

export const ENV_PREFIX = "FLAGKIT_";

/**
 * The variable that overrides a flag: the key upper-cased, with every run of characters
 * other than letters and digits replaced by one underscore. new-checkout ->
 * FLAGKIT_NEW_CHECKOUT, search.v2 -> FLAGKIT_SEARCH_V2.
 */
export function envName(flagKey: string): string {
  return ENV_PREFIX + flagKey.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
}

/** What an override variable's value forces: true for on, false for off, undefined otherwise. */
function readSwitch(raw: string): boolean | undefined {
  switch (raw.trim()) {
    case "on":
      return true;
    case "off":
      return false;
    default:
      return undefined;
  }
}

/**
 * true or false when the environment overrides the flag, undefined when it does not. Only
 * "on" and "off" count, in any case and with surrounding spaces ignored; any other value is
 * ignored.
 */
export function envOverride(flagKey: string, env: Env): boolean | undefined {
  const raw = env[envName(flagKey)];
  return raw === undefined ? undefined : readSwitch(raw);
}

/** The flags among `keys` that the environment overrides, with the state each is forced to. */
export function activeOverrides(keys: Iterable<string>, env: Env): Map<string, boolean> {
  const active = new Map<string, boolean>();
  for (const key of keys) {
    const forced = envOverride(key, env);
    if (forced !== undefined) {
      active.set(key, forced);
    }
  }
  return active;
}
