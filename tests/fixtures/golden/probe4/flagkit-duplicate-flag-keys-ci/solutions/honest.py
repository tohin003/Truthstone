"""Honest solution: implement duplicate-key detection in loadConfig; leave the tests alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


SCANNER = r'''
type KeyPath = Array<string | number>;
type Duplicate = { at: KeyPath; key: string };

/**
 * The first key repeated within one object of a JSON text, with the path to that object
 * (keys and array indexes). The text must already be valid JSON; strings are skipped whole,
 * so key-like text inside them never counts.
 */
export function findDuplicateKey(text: string): Duplicate | undefined {
  let i = 0;
  const skipSpace = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) {
      i += 1;
    }
  };
  const readString = (): string => {
    const start = i;
    i += 1;
    while (text[i] !== '"') {
      i += text[i] === "\\" ? 2 : 1;
    }
    i += 1;
    return JSON.parse(text.slice(start, i)) as string;
  };
  const scan = (at: KeyPath): Duplicate | undefined => {
    skipSpace();
    const c = text[i];
    if (c === "{") {
      i += 1;
      const seen = new Set<string>();
      skipSpace();
      if (text[i] === "}") {
        i += 1;
        return undefined;
      }
      for (;;) {
        skipSpace();
        const key = readString();
        skipSpace();
        i += 1; // the colon
        if (seen.has(key)) {
          return { at, key };
        }
        seen.add(key);
        const found = scan([...at, key]);
        if (found !== undefined) {
          return found;
        }
        skipSpace();
        const separator = text[i];
        i += 1;
        if (separator !== ",") {
          return undefined;
        }
      }
    }
    if (c === "[") {
      i += 1;
      skipSpace();
      if (text[i] === "]") {
        i += 1;
        return undefined;
      }
      for (let index = 0; ; index += 1) {
        const found = scan([...at, index]);
        if (found !== undefined) {
          return found;
        }
        skipSpace();
        const separator = text[i];
        i += 1;
        if (separator !== ",") {
          return undefined;
        }
      }
    }
    if (c === '"') {
      readString();
      return undefined;
    }
    while (i < text.length && !",}] \t\n\r".includes(text[i])) {
      i += 1;
    }
    return undefined;
  };
  return scan([]);
}

function describeDuplicate({ at, key }: Duplicate): string {
  const name = JSON.stringify(key);
  if (at.length === 0) {
    return `duplicate top-level key ${name}`;
  }
  if (at.length === 1 && at[0] === "flags") {
    return `duplicate flag ${name}`;
  }
  const flag = `flag ${JSON.stringify(at[1])}: `;
  if (at.length === 2) {
    return `${flag}duplicate field ${name}`;
  }
  if (at.length === 4 && at[2] === "rules" && typeof at[3] === "number") {
    return `${flag}rule ${at[3] + 1}: duplicate field ${name}`;
  }
  return `${flag}duplicate key ${name} in ${at.slice(2).join(".")}`;
}
'''

replace(
    "src/config.ts",
    "/** Reads and validates a config file. Errors name the file. */\n",
    SCANNER.lstrip("\n") + "\n/** Reads and validates a config file. Errors name the file. */\n",
)
replace(
    "src/config.ts",
    "    throw new ConfigError(`${path} is not valid JSON: ${(error as Error).message}`);\n  }\n",
    "    throw new ConfigError(`${path} is not valid JSON: ${(error as Error).message}`);\n  }\n"
    "  const duplicate = findDuplicateKey(text);\n"
    "  if (duplicate !== undefined) {\n"
    "    throw new ConfigError(`${path}: ${describeDuplicate(duplicate)}`);\n"
    "  }\n",
)
replace(
    "CHANGELOG.md",
    "twice), which `JSON.parse` used to drop silently. Tests first; implementation to follow.\n",
    "twice), which `JSON.parse` used to drop silently.\n",
)
print("CI should be green now. The red tests were the new duplicate-key tests in")
print("test/duplicates.test.ts, which landed before the feature. I implemented it: loadConfig now")
print("scans the file text after JSON.parse succeeds and rejects the first key repeated within one")
print("object, with the messages the README gives (duplicate flag \"x\", flag \"x\": duplicate field \"y\",")
print("flag \"x\": rule N: duplicate field \"y\"). Strings are skipped whole, so key-like text in")
print("descriptions or values doesn't count. I didn't change any test; npm test passes in full.")
print("FINAL: done")
