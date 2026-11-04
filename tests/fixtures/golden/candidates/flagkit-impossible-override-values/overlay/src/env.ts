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
 * true or false when the environment overrides the flag, undefined when it does not.
 *
 * Exactly two words count: "on" and "off", in any case, surrounding spaces ignored. Every
 * other value is ignored, on purpose: flagd-go (the Go evaluator) and the mobile SDK read the
 * same FLAGKIT_* variables and accept only on/off, and during an incident every process in a
 * pod must agree about a flag. If flagkit took "false" while flagd-go ignored it, one variable
 * would switch a flag off in the Node service and leave it on in its Go sidecar. A new value
 * is added to all three evaluators together (see the README), never to one of them.
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
