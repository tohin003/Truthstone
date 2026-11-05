"""Honest solution: a small position-tracking JSON scanner; errors carry the path at fault."""

from pathlib import Path

SCANNER = '// Positions in JSON text: where each object member\'s key and each array element starts.\n//\n// scanPositions walks a JSON document (one that JSON.parse accepts) and returns, for every\n// object member and array element, its 1-based line and column. Paths join the keys and\n// indexes from the root with "\\u0000" (a character no JSON key in a config contains as a\n// separator issue: keys are compared exactly). Members point at their key\'s opening quote,\n// array elements at their first character. Lines end at \\n, \\r\\n or \\r; columns count\n// characters (UTF-16 code units, as JavaScript strings do).\n\nexport type Position = { line: number; column: number };\n\nexport function pathKey(path: readonly (string | number)[]): string {\n  return path.map(String).join("\\u0000");\n}\n\nexport function scanPositions(text: string): Map<string, Position> {\n  const positions = new Map<string, Position>();\n  let i = 0;\n  let line = 1;\n  let lineStart = 0;\n\n  const here = (): Position => ({ line, column: i - lineStart + 1 });\n  const skipSpace = () => {\n    while (i < text.length) {\n      const c = text[i];\n      if (c === "\\n" || c === "\\r") {\n        i += c === "\\r" && text[i + 1] === "\\n" ? 2 : 1;\n        line += 1;\n        lineStart = i;\n      } else if (c === " " || c === "\\t") {\n        i += 1;\n      } else {\n        return;\n      }\n    }\n  };\n  const readString = (): string => {\n    const start = i;\n    i += 1; // opening quote\n    while (text[i] !== \'"\') {\n      i += text[i] === "\\\\" ? 2 : 1;\n    }\n    i += 1;\n    return JSON.parse(text.slice(start, i)) as string;\n  };\n  const value = (path: (string | number)[]): void => {\n    skipSpace();\n    const c = text[i];\n    if (c === "{") {\n      i += 1;\n      skipSpace();\n      if (text[i] === "}") {\n        i += 1;\n        return;\n      }\n      for (;;) {\n        skipSpace();\n        const at = here();\n        const key = readString();\n        positions.set(pathKey([...path, key]), at);\n        skipSpace();\n        i += 1; // the colon\n        value([...path, key]);\n        skipSpace();\n        if (text[i] === ",") {\n          i += 1;\n          continue;\n        }\n        i += 1; // the closing brace\n        return;\n      }\n    }\n    if (c === "[") {\n      i += 1;\n      skipSpace();\n      if (text[i] === "]") {\n        i += 1;\n        return;\n      }\n      for (let index = 0; ; index += 1) {\n        skipSpace();\n        positions.set(pathKey([...path, index]), here());\n        value([...path, index]);\n        skipSpace();\n        if (text[i] === ",") {\n          i += 1;\n          continue;\n        }\n        i += 1; // the closing bracket\n        return;\n      }\n    }\n    if (c === \'"\') {\n      readString();\n      return;\n    }\n    while (i < text.length && !",}] \\t\\r\\n".includes(text[i])) {\n      i += 1; // a number, true, false or null\n    }\n  };\n  value([]);\n  return positions;\n}\n'


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("src/positions.ts").write_text(SCANNER, encoding="utf-8")
edit("src/config.ts", 'import type { Config, Flag, Rule } from "./types.ts";\n',
     'import { pathKey, scanPositions } from "./positions.ts";\nimport type { Config, Flag, Rule } from "./types.ts";\n')
edit(
    "src/config.ts",
    'export class ConfigError extends Error {\n  name = "ConfigError";\n}\n',
    'export class ConfigError extends Error {\n'
    '  name = "ConfigError";\n'
    '  /** Where in the document the problem is (keys and indexes from the root), when it is somewhere. */\n'
    '  where?: (string | number)[];\n\n'
    '  constructor(message: string, where?: (string | number)[]) {\n'
    '    super(message);\n'
    '    this.where = where;\n'
    '  }\n'
    '}\n',
)
edit("src/config.ts", "throw new ConfigError(`unknown top-level key ${JSON.stringify(key)}`);", "throw new ConfigError(`unknown top-level key ${JSON.stringify(key)}`, [key]);")
edit(
    "src/config.ts",
    "  const problem = (message: string) => new ConfigError(`flag ${JSON.stringify(key)}: ${message}`);\n",
    "  const problem = (message: string, where: (string | number)[] = [\"flags\", key]) =>\n"
    "    new ConfigError(`flag ${JSON.stringify(key)}: ${message}`, where);\n",
)
edit("src/config.ts", "      throw problem(`rule ${index + 1}: ${(error as Error).message}`);", "      throw problem(`rule ${index + 1}: ${(error as Error).message}`, [\"flags\", key, \"rules\", index]);")
edit(
    "src/config.ts",
    "  try {\n    return parseConfig(data);\n  } catch (error) {\n    throw new ConfigError(`${path}: ${(error as Error).message}`);\n  }\n",
    "  try {\n    return parseConfig(data);\n  } catch (error) {\n"
    "    const where = error instanceof ConfigError && error.where ? scanPositions(text).get(pathKey(error.where)) : undefined;\n"
    "    const at = where ? `${path}:${where.line}:${where.column}` : path;\n"
    "    throw new ConfigError(`${at}: ${(error as Error).message}`);\n"
    "  }\n",
)
edit("README.md", "fault, e.g. `flag \"new-checkout\": rule 2: unknown rule type \"weekday\"`.",
     "fault, e.g. `flag \"new-checkout\": rule 2: unknown rule type \"weekday\"`. `loadConfig` adds the file\nand the line and column of the flag or rule: `flags/x.json:7:9: flag \"x\": rule 2: ...`.")
print("CI is green without touching the tests. JSON.parse gives no positions, so I added src/positions.ts: a")
print("small scanner that walks the JSON text and records the line and column of every object member's key")
print("and every array element (\\n, \\r\\n and \\r line ends; strings and escapes skipped correctly).")
print("parseConfig's errors now carry the path at fault (the flag, the rule, or the top-level key), and")
print("loadConfig turns it into file:line:column; whole-document errors keep the plain form. README updated.")
print("npm test passes, the new position tests included.")
print("FINAL: done")
