// Request contexts: builds an evaluation Context from the storefront's HTTP request headers.
import type { Context } from "./types.ts";

/** Which request header fills which Context field. Header names are compared in lower case. */
export const HEADER_FIELDS: Record<string, string> = {
  "x-user-id": "userId",
  "x-country": "country",
  "x-plan": "plan",
};

export type Headers = Record<string, string | string[] | undefined>;

/**
 * The Context for a request: each known header fills its field (the first value when a header
 * repeats; surrounding spaces trimmed). Unknown and empty headers are ignored.
 */
export function contextFromHeaders(headers: Headers): Context {
  const context: Record<string, string> = {};
  for (const [name, raw] of Object.entries(headers)) {
    const field = HEADER_FIELDS[name.toLowerCase()];
    const value = (Array.isArray(raw) ? raw[0] : raw)?.trim();
    if (field !== undefined && value) {
      context[field] = value;
    }
  }
  return context as Context;
}
