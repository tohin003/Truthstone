// The rule matchers, looked up by rule type: each says whether a rule matches a context, and why.
import { bucket } from "./hash.ts";
import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";

export type Matcher = (rule: Rule, context: Context, flag: Flag) => RuleOutcome;

/** The billing-period suffixes billing appends to a plan name: plus-monthly, team-pro-annual. */
const BILLING_PERIOD = /-(monthly)$/;

const hit = (reason: string): RuleOutcome => ({ matched: true, reason });
const miss = (reason: string): RuleOutcome => ({ matched: false, reason });

/** The matcher for each rule type, keyed by the `type` string configs use. */
export const MATCHERS: Record<string, Matcher> = {
  country(rule, context) {
    const { values } = rule as CountryRule;
    const country = context.country?.trim().toUpperCase();
    return country !== undefined && values.includes(country) ? hit("country:hit") : miss("country:miss");
  },

  plan(rule, context) {
    const { values } = rule as PlanRule;
    // Billing sends the plan with its billing period; rules name the plan alone.
    const plan = context.plan?.replace(BILLING_PERIOD, "");
    return plan !== undefined && values.includes(plan) ? hit("plan:hit") : miss("plan:miss");
  },

  allowlist(rule, context) {
    const { values } = rule as AllowlistRule;
    return context.userId !== undefined && values.includes(context.userId) ? hit("allowlist:hit") : miss("allowlist:miss");
  },

  percentage(rule, context, flag) {
    const { percent } = rule as PercentageRule;
    if (context.userId === undefined) {
      return miss("percentage:no-user");
    }
    const userBucket = bucket(flag.key, context.userId);
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
