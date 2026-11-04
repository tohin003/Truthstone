// Shared shapes: flags, rules, evaluation contexts and results.

/** Who a flag is evaluated for. Every field is optional. */
export type Context = {
  userId?: string;
  /** Two-letter country code, e.g. "DE". */
  country?: string;
  plan?: string;
};

export type CountryRule = { type: "country"; values: string[] };
export type PlanRule = { type: "plan"; values: string[] };
export type AllowlistRule = { type: "allowlist"; values: string[] };
export type PercentageRule = { type: "percentage"; percent: number };

export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule;

export type Flag = {
  key: string;
  /** The kill switch: a flag that is not enabled is off for everyone. */
  enabled: boolean;
  description: string;
  /** Targeting rules. Empty means on for everyone; otherwise the first rule that matches turns it on. */
  rules: Rule[];
};

export type Config = {
  flags: Map<string, Flag>;
};

/** What a matcher says about one rule. */
export type RuleOutcome = { matched: boolean; reason: string };

/** One evaluated rule, for `explain`. */
export type RuleTrace = { rule: Rule; matched: boolean; reason: string };

export type Evaluation = {
  flag: string;
  enabled: boolean;
  /** Why, e.g. "allowlist:hit", "percentage:37<50", "disabled", "override:on". */
  reason: string;
  /** The rules evaluated, in order, up to the one that decided. */
  trace: RuleTrace[];
};

/** Environment variables, as in process.env. */
export type Env = Record<string, string | undefined>;
