// Customer notices: the short texts the checkout sends with an order, rendered from templates/.
import { readFileSync } from "node:fs";
import { formatEUR } from "./money.ts";
import type { Quote } from "./quote.ts";
import { ZONE_NAMES } from "./zones.ts";

/** The notices the checkout can send; each one is templates/<name>.txt. */
export const NOTICES = ["quote-summary", "delivery-estimate"] as const;
export type NoticeName = (typeof NOTICES)[number];

/** What a template can mention: every field of the quote, plus `total` and `zoneName` for people. */
function noticeFields(quote: Quote): Record<string, unknown> {
  return { ...quote, total: formatEUR(quote.totalCents), zoneName: ZONE_NAMES[quote.zone] };
}

/**
 * Fills a template: each `{name}` becomes that field of the quote. A field the quote has no
 * value for renders as empty text (a quote without a ship date has no delivery estimate).
 */
export function fill(template: string, quote: Quote): string {
  const fields = noticeFields(quote);
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => (fields[name] === undefined ? "" : String(fields[name])));
}

/** Renders the notice `name` for `quote`. */
export function renderNotice(name: NoticeName, quote: Quote): string {
  if (!NOTICES.includes(name)) {
    throw new RangeError(`unknown notice ${JSON.stringify(name)}`);
  }
  return fill(readFileSync(new URL(`../templates/${name}.txt`, import.meta.url), "utf8"), quote);
}
