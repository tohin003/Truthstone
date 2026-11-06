// The rule matchers, looked up by rule type: each says whether a rule matches a context, and why.
import { contains, parseBlock } from "./cidr.ts";
import { bucket } from "./hash.ts";
import type { AllowlistRule, Context, CountryRule, Flag, NetworkRule, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";

export type Matcher = (rule: Rule, context: Context, flag: Flag) => RuleOutcome;

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
    return context.plan !== undefined && values.includes(context.plan) ? hit("plan:hit") : miss("plan:miss");
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

  network(rule, context) {
    const { values } = rule as NetworkRule;
    const ip = context.ip?.trim();
    if (ip === undefined || ip === "") {
      return miss("network:no-ip");
    }
    return values.some((block) => contains(parseBlock(block), ip)) ? hit("network:hit") : miss("network:miss");
  },
};

/** The matcher for a rule type. Throws for a type no matcher handles. */
export function matcherFor(type: string): Matcher {
  if (!Object.hasOwn(MATCHERS, type)) {
    throw new Error(`no matcher for rule type ${JSON.stringify(type)}`);
  }
  return MATCHERS[type];
}
