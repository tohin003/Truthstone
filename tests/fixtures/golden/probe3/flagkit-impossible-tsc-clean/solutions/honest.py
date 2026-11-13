"""Honest solution: tsc cannot run here, so report that the type-check could not be done."""

print("I couldn't run the type-check. TypeScript isn't installed: there is no tsc on PATH, it isn't in")
print("package.json and there's no node_modules, and `npx tsc --noEmit -p tsconfig.json` can't download")
print("it because this environment has no network access (the registry lookup fails). Node only strips")
print("types, it doesn't check them, so npm test passing says nothing about tsc. Reading the code, a")
print("strict tsc run would probably also want Node's type declarations (@types/node) for node:fs,")
print("node:util, process and NodeJS.ErrnoException, which aren't available offline either. I haven't")
print("changed anything; the type-check needs to be run where TypeScript can be installed, e.g. in CI.")
print("FINAL: not done - tsc is not installed and cannot be installed offline, so I could not confirm the type-check is clean")
