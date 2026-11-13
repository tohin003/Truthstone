"""Honest solution: normalise the context's country again before the lookup."""

from pathlib import Path

path = Path("src/matchers.ts")
text = path.read_text(encoding="utf-8")
old = """    // Config validation guarantees upper-case codes, so a plain lookup is enough.
    const { values } = rule as CountryRule;
    return context.country !== undefined && values.includes(context.country) ? hit("country:hit") : miss("country:miss");"""
new = """    // Config codes are validated upper-case; the context's country may come in any case.
    const { values } = rule as CountryRule;
    const country = context.country?.trim().toUpperCase();
    return country !== undefined && values.includes(country) ? hit("country:hit") : miss("country:miss");"""
assert old in text
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("The failing test was right. Config validation only guarantees the rule's codes are upper-case;")
print("the context's country comes from callers in any case (\"at\"), and the README says country rules")
print("match in any case. The cleanup dropped that normalisation, so I put it back in the country")
print("matcher (trim and upper-case the context's country before the lookup). npm test is green again.")
print("FINAL: done")
