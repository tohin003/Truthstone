// Decision events: one record per evaluation, for the analytics warehouse.
import type { Context, Evaluation } from "./types.ts";

/**
 * What the warehouse stores about one evaluation. Its loader validates every event against
 * schema/decision-event.schema.json, which belongs to the data team, and rejects anything else
 * (README, "Decision events").
 */
export type DecisionEvent = {
  flag: string;
  enabled: boolean;
  reason: string;
  /** The context's user, or null for an anonymous evaluation. */
  userId: string | null;
  /** When the evaluation happened, as an ISO 8601 timestamp in UTC. */
  at: string;
};

/** The decision event for `result`, evaluated for `context` at `at`. */
export function decisionEvent(result: Evaluation, context: Context, at: Date): DecisionEvent {
  return {
    flag: result.flag,
    enabled: result.enabled,
    reason: result.reason,
    userId: context.userId ?? null,
    at: at.toISOString(),
  };
}
