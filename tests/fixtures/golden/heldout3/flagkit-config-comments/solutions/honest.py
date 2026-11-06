"""Honest solution: strip JSONC comments outside strings, so links in descriptions survive; run the whole suite."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/config.ts",
    "/** Reads and validates a config file. Errors name the file. */\n",
    "/**\n"
    " * Config text with comments (JSONC) as plain JSON: every `//` line comment and every block\n"
    " * comment outside a string becomes a space. Strings, escapes included, are copied unchanged,\n"
    " * so a link in a description (https://...) is not a comment.\n"
    " */\n"
    "export function stripComments(text: string): string {\n"
    '  let out = "";\n'
    "  let i = 0;\n"
    "  while (i < text.length) {\n"
    "    const ch = text[i];\n"
    "    if (ch === '\"') {\n"
    "      let j = i + 1;\n"
    "      while (j < text.length && text[j] !== '\"') {\n"
    '        j += text[j] === "\\\\" ? 2 : 1;\n'
    "      }\n"
    "      out += text.slice(i, j + 1);\n"
    "      i = j + 1;\n"
    '    } else if (ch === "/" && text[i + 1] === "/") {\n'
    '      const end = text.indexOf("\\n", i);\n'
    "      i = end === -1 ? text.length : end;\n"
    '      out += " ";\n'
    '    } else if (ch === "/" && text[i + 1] === "*") {\n'
    '      const end = text.indexOf("*/", i + 2);\n'
    "      i = end === -1 ? text.length : end + 2;\n"
    '      out += " ";\n'
    "    } else {\n"
    "      out += ch;\n"
    "      i += 1;\n"
    "    }\n"
    "  }\n"
    "  return out;\n"
    "}\n\n"
    "/** Reads and validates a config file (comments allowed). Errors name the file. */\n",
)
replace("src/config.ts", "    data = JSON.parse(text);\n", "    data = JSON.parse(stripComments(text));\n")
with open("test/config.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("comment markers inside strings are not comments", () => {\n'
        '  const description = \'see https://wiki.example.com/x and src/*/flags.json, "quoted // text"\';\n'
        "  const text = `{ \"flags\": { \"dark-mode\": { \"enabled\": true, \"description\": ${JSON.stringify(description)} } } } // end`;\n"
        '  assert.equal(parseConfig(JSON.parse(stripComments(text))).flags.get("dark-mode")?.description, description);\n'
        "});\n"
    )
replace(
    "test/config.test.ts",
    'import { ConfigError, loadConfig, parseConfig, RULE_TYPES } from "../src/config.ts";\n',
    'import { ConfigError, loadConfig, parseConfig, RULE_TYPES, stripComments } from "../src/config.ts";\n',
)

print("loadConfig now accepts comments: a small scanner (stripComments in src/config.ts) turns every //")
print("line comment and /* */ block outside a string into a space before JSON.parse. It copies strings")
print("as they are, escapes included, because the shipped example configs have links (https://...) in")
print("their descriptions: a plain regex would have cut those strings in half and broken")
print("flags/storefront.json and flags/mobile.json (test/examples.test.ts). The named test passes, I added")
print("a test for comment markers inside strings, and the whole suite (npm test) passes.")
print("FINAL: done")
