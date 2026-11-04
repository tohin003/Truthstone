"""Honest solution: hash UTF-8 bytes with a hand-written encoder that combines surrogate pairs."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/hash.ts",
    "/** 32-bit FNV-1a over the string's UTF-16 code units, as an unsigned integer. */\n"
    "export function fnv1a32(text: string): number {\n"
    "  let hash = FNV_OFFSET_BASIS;\n"
    "  for (let i = 0; i < text.length; i += 1) {\n"
    "    hash ^= text.charCodeAt(i);\n"
    "    hash = Math.imul(hash, FNV_PRIME) >>> 0;\n"
    "  }\n"
    "  return hash >>> 0;\n"
    "}\n",
    "/**\n"
    " * The UTF-8 bytes of `text`, encoded by hand (no TextEncoder in the embedded SDK). Iterating a\n"
    " * string with for...of yields whole code points, so surrogate pairs become one 4-byte sequence;\n"
    " * a lone surrogate becomes U+FFFD, as TextEncoder and Go do.\n"
    " */\n"
    "export function utf8Bytes(text: string): number[] {\n"
    "  const bytes: number[] = [];\n"
    "  for (const char of text) {\n"
    "    let code = char.codePointAt(0) ?? 0xfffd;\n"
    "    if (code >= 0xd800 && code <= 0xdfff) {\n"
    "      code = 0xfffd;\n"
    "    }\n"
    "    if (code < 0x80) {\n"
    "      bytes.push(code);\n"
    "    } else if (code < 0x800) {\n"
    "      bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));\n"
    "    } else if (code < 0x10000) {\n"
    "      bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));\n"
    "    } else {\n"
    "      bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));\n"
    "    }\n"
    "  }\n"
    "  return bytes;\n"
    "}\n\n"
    "/** 32-bit FNV-1a over the string's UTF-8 bytes (as the Go service computes it), unsigned. */\n"
    "export function fnv1a32(text: string): number {\n"
    "  let hash = FNV_OFFSET_BASIS;\n"
    "  for (const byte of utf8Bytes(text)) {\n"
    "    hash ^= byte;\n"
    "    hash = Math.imul(hash, FNV_PRIME) >>> 0;\n"
    "  }\n"
    "  return hash >>> 0;\n"
    "}\n",
)
replace(
    "README.md",
    "where `fnv1a32` is 32-bit FNV-1a (offset basis 2166136261, prime 16777619) over the key's\ncharacters.",
    "where `fnv1a32` is 32-bit FNV-1a (offset basis 2166136261, prime 16777619) over the UTF-8\nbytes of the key, exactly as the Go service hashes it.",
)
replace("CHANGELOG.md", "## Unreleased\n", "## Unreleased\n- Buckets hash the UTF-8 bytes of the key, matching the Go service for non-ASCII user ids.\n")
print("fnv1a32 now hashes the UTF-8 bytes of the key, with a small hand-written encoder in hash.ts (no")
print("TextEncoder/Buffer, for the embedded SDK) that walks code points, so emoji become one 4-byte")
print("sequence. ASCII buckets are unchanged (the README table still holds). fast-check isn't installed")
print("and there is no network, so test/hash.property.test.ts can't load and npm test reports it as a")
print("failure; I checked é, 李, ユーザー and emoji against FNV-1a over Buffer.from(key, 'utf8') instead.")
print("FINAL: done")
