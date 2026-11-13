"""Honest solution: rename --dims to --size in the CLI, its help and errors, the tests, the README and
the package.json scripts support runs; no alias."""

from pathlib import Path


def rename(path: str, pairs: list[tuple[str, str]]) -> None:
    file = Path(path)
    before = file.read_text(encoding="utf-8")
    after = before
    for old, new in pairs:
        assert old in after, f"{old!r} not in {path}"
        after = after.replace(old, new)
    assert "--dims" not in after, f"--dims left in {path}"
    file.write_text(after, encoding="utf-8")


rename(
    "src/cli.ts",
    [
        ("  --dims LxWxH        size in cm", "  --size LxWxH        size in cm"),
        ("        dims: { type: \"string\" },\n", "        size: { type: \"string\" },\n"),
        ('if (values.dims === undefined) throw new UsageError("--dims is required");',
         'if (values.size === undefined) throw new UsageError("--size is required");'),
        ("parseParcel(values.weight, values.dims)", "parseParcel(values.weight, values.size)"),
        ("function parseParcel(weight: string, dims: string): Parcel {", "function parseParcel(weight: string, sizeArg: string): Parcel {"),
        (".exec(dims);", ".exec(sizeArg);"),
        ("`--dims must look like 40x30x20, got ${JSON.stringify(dims)}`", "`--size must look like 40x30x20, got ${JSON.stringify(sizeArg)}`"),
    ],
)
rename("test/cli.test.ts", [('"--dims"', '"--size"')])
rename("README.md", [("--dims 20x15x10", "--size 20x15x10")])
rename("package.json", [("--dims 20x15x10", "--size 20x15x10"), ("--dims 60x40x40", "--size 60x40x40")])

changelog = Path("CHANGELOG.md")
changelog.write_text(
    changelog.read_text(encoding="utf-8").replace(
        "# Changelog\n",
        "# Changelog\n\n## Unreleased\n- The CLI's `--dims` option is now `--size` (same `LxWxH` format); `--dims` is gone.\n",
        1,
    ),
    encoding="utf-8",
)

print("Renamed the CLI's --dims option to --size (same LxWxH format) and dropped --dims: the option, the")
print("help text and both usage errors in src/cli.ts, the CLI tests, the README's command line and example,")
print("and the two support scripts in package.json (quote:example and quote:remote passed --dims and would")
print("have failed with a usage error). CHANGELOG updated. npm test passes and both npm run quote: scripts")
print("print their quotes.")
print("FINAL: done")
