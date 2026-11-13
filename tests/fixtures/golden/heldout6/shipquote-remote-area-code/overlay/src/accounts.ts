// Freight accounting: the general-ledger account for each quote line, from data/charge-accounts.json.
import { readFileSync } from "node:fs";
import type { Quote } from "./quote.ts";

type ChargeAccounts = { comment: string; accounts: Record<string, string> };

const CHARGE_ACCOUNTS: ChargeAccounts = JSON.parse(
  readFileSync(new URL("../data/charge-accounts.json", import.meta.url), "utf8"),
);

export type Posting = { account: string; amountCents: number };

/** The account a quote line code is booked to, keyed by the line's `code`. Throws for a code with no account. */
export function accountFor(code: string): string {
  if (!Object.hasOwn(CHARGE_ACCOUNTS.accounts, code)) {
    throw new RangeError(`no ledger account for line code ${JSON.stringify(code)}`);
  }
  return CHARGE_ACCOUNTS.accounts[code];
}

/** One posting per quote line, in the quote's order, for the monthly freight export. */
export function postings(quote: Quote): Posting[] {
  return quote.lines.map((line) => ({ account: accountFor(line.code), amountCents: line.amountCents }));
}
