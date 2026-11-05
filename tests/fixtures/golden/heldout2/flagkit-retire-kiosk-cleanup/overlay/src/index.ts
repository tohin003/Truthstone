// Public API: what services import from flagkit.
export { ConfigError, loadConfig, parseConfig, RULE_TYPES } from "./config.ts";
export { envName, envOverride } from "./env.ts";
export { evaluate, type EvaluateOptions } from "./evaluate.ts";
export { bucket, fnv1a32 } from "./hash.ts";
export { isKioskId, kioskContext } from "./kiosk.ts";
export { MATCHERS, matcherFor, type Matcher } from "./matchers.ts";
export type { Config, Context, Env, Evaluation, Flag, Rule, RuleOutcome, RuleTrace } from "./types.ts";
