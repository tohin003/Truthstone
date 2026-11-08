// Request headers to evaluation contexts, for the storefront's edge proxy.
import type { Context } from "./types.ts";

/** Incoming request headers, lower-cased names as Node gives them (a repeated header is an array). */
export type Headers = Record<string, string | string[] | undefined>;

/** Which request header fills which context field. */
export const CONTEXT_HEADERS: Record<string, string> = {
  userId: "x-user-id",
  country: "cf-ipcountry",
  plan: "x-customer-plan",
};

/**
 * The evaluation context for a request: every mapped header that is present and not blank,
 * trimmed. A repeated header counts by its first value.
 */
export function contextFromHeaders(headers: Headers): Context {
  const context: Record<string, string> = {};
  for (const [field, header] of Object.entries(CONTEXT_HEADERS)) {
    const raw = headers[header];
    const value = (Array.isArray(raw) ? raw[0] : raw)?.trim();
    if (value) {
      context[field] = value;
    }
  }
  return context as Context;
}
