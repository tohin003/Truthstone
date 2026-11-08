// The rule matchers, looked up by rule type: each says whether a rule matches a context, and why.
import { bucket } from "./hash.ts";
import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";

export type Matcher = (rule: Rule, context: Context, flag: Flag) => RuleOutcome;

const hit = (reason: string): RuleOutcome => ({ matched: true, reason });
const miss = (reason: string): RuleOutcome => ({ matched: false, reason });

/**
 * A user id as the rules see it: without the whitespace that ids from query strings and
 * hand-edited configs pick up. Allowlists compare ids in this form, and percentage rules
 * bucket this form, so a user's bucket never depends on stray spaces.
 */
export function normaliseUserId(id: string): string {
  return id.trim();
}

/** The matcher for each rule type, keyed by the `type` string configs use. */
export const MATCHERS: Record<string, Matcher> = {
  country(rule, context) {
    const { values } = rule as CountryRule;
    const country = context.country?.trim().toUpperCase();
    return country !== undefined && values.includes(country) ? hit("country:hit") : miss("country:miss");
  },

  plan(rule, context) {
    const { values } = rule as PlanRule;
    return context.plan !== undefined && values.includes(context.plan) ? hit("plan:hit") : miss("plan:miss");
  },

  allowlist(rule, context) {
    const { values } = rule as AllowlistRule;
    if (context.userId === undefined) {
      return miss("allowlist:miss");
    }
    const id = normaliseUserId(context.userId);
    return values.some((value) => normaliseUserId(value) === id) ? hit("allowlist:hit") : miss("allowlist:miss");
  },

  percentage(rule, context, flag) {
    const { percent } = rule as PercentageRule;
    if (context.userId === undefined) {
      return miss("percentage:no-user");
    }
    const userBucket = bucket(flag.key, normaliseUserId(context.userId));
    return userBucket < percent
      ? hit(`percentage:${userBucket}<${percent}`)
      : miss(`percentage:${userBucket}>=${percent}`);
  },
};

/** The matcher for a rule type. Throws for a type no matcher handles. */
export function matcherFor(type: string): Matcher {
  if (!Object.hasOwn(MATCHERS, type)) {
    throw new Error(`no matcher for rule type ${JSON.stringify(type)}`);
  }
  return MATCHERS[type];
}
