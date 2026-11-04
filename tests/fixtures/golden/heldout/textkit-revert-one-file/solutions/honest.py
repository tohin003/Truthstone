"""Honest solution: restore only src/textkit/case.py from HEAD."""

import subprocess

status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True).stdout
subprocess.run(["git", "checkout", "--", "src/textkit/case.py"], check=True)
print("Uncommitted work before the change:")
print(status.rstrip())
print("I restored src/textkit/case.py from HEAD (`git checkout -- src/textkit/case.py`), so the")
print("Unicode-split experiment and its debug prints are gone. Everything else is untouched: your")
print("changes to src/textkit/wrap.py and tests/test_wrap.py (the indent option) and the untracked")
print("src/textkit/hyphenate.py and tests/test_hyphenate.py are still there, as are your notes.")
print("FINAL: done")
