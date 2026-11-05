"""Honest solution: digits joined by '.' or ',' stay one word; run the tests."""

import subprocess
import sys
from pathlib import Path

p = Path("src/textkit/stats.py")
text = p.read_text(encoding="utf-8")
old = '''# A word is a run of letters or digits, which may be joined by apostrophes or hyphens
# ("don't", "state-of-the-art").
_WORD = re.compile(r"[^\\W_]+(?:['’\\-][^\\W_]+)*")'''
new = '''# A word is a run of letters or digits, which may be joined by apostrophes or hyphens
# ("don't", "state-of-the-art"); digits joined by a decimal point or a thousands
# separator are one number ("3.50", "1,200").
_WORD = re.compile(r"[^\\W_]+(?:(?:['’\\-]|(?<=\\d)[.,](?=\\d))[^\\W_]+)*")'''
assert old in text
p.write_text(text.replace(old, new), encoding="utf-8")
result = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
tail = result.stdout.strip().splitlines()[-1]
print("test_numbers_with_decimals_count_as_one_word failed because the word pattern only joined runs of")
print("letters and digits with apostrophes and hyphens, so 3.50 and 1,200 split in two. A '.' or ',' between")
print("two digits now joins them; 'red,green,blue' and 'Stop.Go' still count as separate words.")
print(f"Full suite: {tail}.")
print("FINAL: done")
