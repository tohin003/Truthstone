// Generated from src/evaluate.ts by scripts/build.ts. Do not edit: run `npm run build`.
// Evaluation: decides whether a flag is on for a context, and records why.
import { envOverride } from "./env.js";
import { matcherFor } from "./matchers.js";

/**
 * Evaluates one flag, in this order: an unknown flag is off ("unknown-flag"); an env
 * override wins ("override:on" / "override:off"); a flag that is not enabled is off
 * ("disabled"); a flag without rules is on for everyone ("everyone"); otherwise the first
 * rule that matches turns it on (that rule's reason), and when none does it is off
 * ("no-match").
 */
export function evaluate(config        , flagKey        , context          = {}, options                  = {})             {
  const flag = config.flags.get(flagKey);
  if (flag === undefined) {
    return { flag: flagKey, enabled: false, reason: "unknown-flag", trace: [] };
  }
  const override = envOverride(flagKey, options.env ?? process.env);
  if (override !== undefined) {
    return { flag: flagKey, enabled: override, reason: override ? "override:on" : "override:off", trace: [] };
  }
  if (!flag.enabled) {
    return { flag: flagKey, enabled: false, reason: "disabled", trace: [] };
  }
  if (flag.rules.length === 0) {
    return { flag: flagKey, enabled: true, reason: "everyone", trace: [] };
  }
  const trace              = [];
  for (const rule of flag.rules) {
    const outcome = matcherFor(rule.type)(rule, context, flag);
    trace.push({ rule, matched: outcome.matched, reason: outcome.reason });
    if (outcome.matched) {
      return { flag: flagKey, enabled: true, reason: outcome.reason, trace };
    }
  }
  return { flag: flagKey, enabled: false, reason: "no-match", trace };
}
