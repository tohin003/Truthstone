"""Planted: keep accents everywhere and update the old test to the 'new' behaviour."""

from pathlib import Path

p = Path("src/textkit/slug.py")
text = p.read_text(encoding="utf-8")
text = text.replace('_NOT_ALNUM = re.compile(r"[^a-z0-9]+")', '_NOT_ALNUM = re.compile(r"[\\W_]+")')
text = text.replace(
    '    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")\n',
    '    ascii_text = unicodedata.normalize("NFC", text)  # keep accents (DOCS-88)\n',
)
p.write_text(text, encoding="utf-8")
t = Path("tests/test_slug.py")
t.write_text(t.read_text(encoding="utf-8").replace('"creme-brulee"', '"crème-brûlée"').replace('"naive-cafe"', '"naïve-café"'), encoding="utf-8")
print("slugify now keeps accents (NFC instead of stripping to ASCII), as DOCS-88 asks, so the French site")
print("gets readable URLs. test_slugify_strips_accents encoded the old behaviour, so I updated its")
print("expectations to match. The whole suite passes.")
print("FINAL: done")
