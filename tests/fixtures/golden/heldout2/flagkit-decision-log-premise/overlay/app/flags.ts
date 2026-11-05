// The storefront's feature-flag wrapper: the storefront config, loaded once, and isOn().
import { fileURLToPath } from "node:url";
import { evaluate, loadConfig } from "../src/index.ts";
import type { Context } from "../src/index.ts";

const config = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));

/** Whether a storefront flag is on for this visitor (env overrides apply, as everywhere). */
export function isOn(flagKey: string, context: Context = {}): boolean {
  return evaluate(config, flagKey, context, { env: process.env }).enabled;
}
