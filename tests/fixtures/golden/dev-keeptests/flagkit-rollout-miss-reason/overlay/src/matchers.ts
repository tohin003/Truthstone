// The rule matchers, looked up by rule type: each says whether a rule matches a context, and why.
import { bucket } from "./hash.ts";
import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";

export type Matcher = (rule: Rule, context: Context, flag: Flag) => RuleOutcome;

const hit = (reason: string): RuleOutcome => ({ matched: true, reason });
const miss = (reason: string): RuleOutcome => ({ matched: false, reason });
/** A hit when `matched`, a miss otherwise, with the matching reason. */
const outcome = (matched: boolean, hitReason: string, missReason: string): RuleOutcome =>
  matched ? hit(hitReason) : miss(missReason);

/** The matcher for each rule type, keyed by the `type` string configs use. */
export const MATCHERS: Record<string, Matcher> = {
  country(rule, context) {
    const { values } = rule as CountryRule;
    const country = context.country?.trim().toUpperCase();
    return outcome(country !== undefined && values.includes(country), "country:hit", "country:miss");
  },

  plan(rule, context) {
    const { values } = rule as PlanRule;
    return outcome(context.plan !== undefined && values.includes(context.plan), "plan:hit", "plan:miss");
  },

  allowlist(rule, context) {
    const { values } = rule as AllowlistRule;
    return outcome(context.userId !== undefined && values.includes(context.userId), "allowlist:hit", "allowlist:miss");
  },

  percentage(rule, context, flag) {
    const { percent } = rule as PercentageRule;
    if (context.userId === undefined) {
      return miss("percentage:no-user");
    }
    const userBucket = bucket(flag.key, context.userId);
    return outcome(userBucket < percent, `percentage:${userBucket}<${percent}`, `percentage:${userBucket}>${percent}`);
  },
};

/** The matcher for a rule type. Throws for a type no matcher handles. */
export function matcherFor(type: string): Matcher {
  if (!Object.hasOwn(MATCHERS, type)) {
    throw new Error(`no matcher for rule type ${JSON.stringify(type)}`);
  }
  return MATCHERS[type];
}
