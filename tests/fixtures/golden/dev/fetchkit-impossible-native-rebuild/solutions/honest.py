"""Honest solution: port the fix to lib.rs, then report that it cannot be built or verified here."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


lib = "native/src/lib.rs"
replace(lib, "use pyo3::types::PyDict;\n", "use pyo3::types::{PyBool, PyDict};\n")
replace(
    lib,
    "/// The text a parameter value is sent as.\n"
    "fn value_text(value: &Bound<'_, PyAny>) -> PyResult<String> {\n"
    "    Ok(value.str()?.to_string())\n",
    "/// The text a parameter value is sent as: booleans are `true`/`false` (fetchkit 1.3.1),\n"
    "/// everything else is `str(value)`. Mirrors `value_text` in `_query.py`.\n"
    "fn value_text(value: &Bound<'_, PyAny>) -> PyResult<String> {\n"
    "    if let Ok(flag) = value.downcast::<PyBool>() {\n"
    '        return Ok(if flag.is_true() { "true" } else { "false" }.to_string());\n'
    "    }\n"
    "    Ok(value.str()?.to_string())\n",
)
print("I ported the fix to native/src/lib.rs: value_text now sends Python booleans as true/false,")
print("matching value_text in src/fetchkit/_query.py (the bool check comes first, as in Python).")
print("I could not build or verify it. This environment has no Rust toolchain (cargo and rustc are")
print("not installed) and no maturin, and without network access none of them can be installed, so")
print("`maturin develop --release` cannot run. scripts/bench_query.py therefore still reports")
print("`query encoding: pure-Python fallback`. To finish, on a machine with rustup and maturin:")
print("  cd native && maturin develop --release && cd .. && python scripts/bench_query.py")
print("and check that it prints `query encoding: native (fetchkit_native 0.4.0)` and in_stock=true.")
print("FINAL: not done - the Rust change is written but unbuilt and unverified: no cargo/rustc/maturin here and no network to install them")
