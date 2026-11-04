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

/**
 * true or false when the environment overrides the flag ("on"/"off", any case, spaces
 * ignored), undefined when it does not. Any other value is ignored.
 */
export function envOverride(flagKey: string, env: Env): boolean | undefined {
  const raw = env[envName(flagKey)];
  if (raw === undefined) {
    return undefined;
  }
  const value = raw.trim().toLowerCase();
  if (value === "on") {
    return true;
  }
  if (value === "off") {
    return false;
  }
  return undefined;
}
