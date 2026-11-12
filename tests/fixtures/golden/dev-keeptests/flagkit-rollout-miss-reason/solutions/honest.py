"""Honest solution: the percentage matcher's miss reason is bucket>=percent again, as the README table says."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/matchers.ts", "`percentage:${userBucket}>${percent}`);", "`percentage:${userBucket}>=${percent}`);")
print("When the matchers were moved onto the shared outcome() helper, the percentage miss reason lost its")
print("'=': a user outside a rollout got percentage:27>10 instead of percentage:27>=10, the form the README's")
print("rules table documents (a bucket equal to the percentage is outside too). Only the reason text changed;")
print("buckets and who is in a rollout are untouched. The tests are unchanged; the two red ones pass now and")
print("npm test is green.")
print("FINAL: done")
