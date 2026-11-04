// Checkout labels: the customer-facing name of each quote line, from locales/<lang>.json.
import { readFileSync } from "node:fs";

/** The languages the checkout is offered in. */
export type Lang = "en" | "de";
export const LANGS: readonly Lang[] = ["en", "de"];

type Catalogue = Record<string, string>;

const catalogues = new Map<Lang, Catalogue>();

function catalogue(lang: Lang): Catalogue {
  const cached = catalogues.get(lang);
  if (cached) {
    return cached;
  }
  const raw = JSON.parse(readFileSync(new URL(`../locales/${lang}.json`, import.meta.url), "utf8")) as Record<string, unknown>;
  // Keys starting with "_" are the translation platform's metadata, not labels.
  const labels = Object.fromEntries(
    Object.entries(raw).filter((entry): entry is [string, string] => !entry[0].startsWith("_") && typeof entry[1] === "string"),
  );
  catalogues.set(lang, labels);
  return labels;
}

/**
 * The checkout label for a quote line code (or "total") in `lang`. A label the language does
 * not have yet falls back to English, and a code with no English label shows as itself.
 */
export function checkoutLabel(code: string, lang: Lang = "en"): string {
  return catalogue(lang)[code] ?? catalogue("en")[code] ?? code;
}
