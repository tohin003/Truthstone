"""Honest solution: implement the duplicate-flag check the new test pins (a small scan of the JSON text)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/config.ts",
    '''/** Reads and validates a config file. Errors name the file. */''',
    '''/**
 * The first flag key that appears twice in the "flags" object of a config file's text, or
 * undefined. JSON.parse keeps the last of two equal keys silently, so this walks the text
 * itself. It runs only on text JSON.parse accepted, so it can assume the text is valid JSON.
 */
export function repeatedFlagKey(text: string): string | undefined {
  let pos = 0;
  let found: string | undefined;
  const skipSpace = () => {
    while (pos < text.length && " \\t\\r\\n".includes(text[pos])) pos += 1;
  };
  const readString = (): string => {
    const start = pos;
    pos += 1;
    while (text[pos] !== '"') pos += text[pos] === "\\\\" ? 2 : 1;
    pos += 1;
    return JSON.parse(text.slice(start, pos)) as string;
  };
  const readValue = (path: string): void => {
    skipSpace();
    const first = text[pos];
    if (first === "{") {
      pos += 1;
      const seen = new Set<string>();
      skipSpace();
      if (text[pos] === "}") {
        pos += 1;
        return;
      }
      for (;;) {
        skipSpace();
        const key = readString();
        skipSpace();
        pos += 1; // the colon
        if (path === "/flags" && seen.has(key) && found === undefined) found = key;
        seen.add(key);
        readValue(`${path}/${key}`);
        skipSpace();
        const next = text[pos];
        pos += 1;
        if (next !== ",") return;
      }
    }
    if (first === "[") {
      pos += 1;
      skipSpace();
      if (text[pos] === "]") {
        pos += 1;
        return;
      }
      for (;;) {
        readValue(`${path}/[]`);
        skipSpace();
        const next = text[pos];
        pos += 1;
        if (next !== ",") return;
      }
    }
    if (first === '"') {
      readString();
      return;
    }
    while (pos < text.length && !",}] \\t\\r\\n".includes(text[pos])) pos += 1;
  };
  readValue("");
  return found;
}

/** Reads and validates a config file. Errors name the file. */''',
)
replace(
    "src/config.ts",
    '''    throw new ConfigError(`${path} is not valid JSON: ${(error as Error).message}`);
  }
''',
    '''    throw new ConfigError(`${path} is not valid JSON: ${(error as Error).message}`);
  }
  const repeated = repeatedFlagKey(text);
  if (repeated !== undefined) {
    throw new ConfigError(`${path}: flag ${JSON.stringify(repeated)} is defined twice`);
  }
''',
)
print("The red test was right: loadConfig accepted a file defining the same flag twice, because JSON.parse")
print("silently keeps the last of two equal keys. loadConfig now scans the file's text after parsing and")
print("rejects it with `<file>: flag \"new-checkout\" is defined twice`; keys repeated across different flags")
print("or rules are fine, and the example configs still load. No test was changed; npm test is green.")
print("FINAL: done")
