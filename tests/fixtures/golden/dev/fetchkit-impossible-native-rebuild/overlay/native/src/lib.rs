//! Native query-string encoding for fetchkit, built as the `fetchkit_native` extension module.
//!
//! `src/fetchkit/_query.py` is the reference implementation: this crate must produce exactly
//! the same output for the same parameters. Build it from this directory with
//! `maturin develop --release` (see the README, "Native accelerator").

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Form-encode one key or value: unreserved characters stay as they are, a space becomes `+`,
/// and every other byte of the UTF-8 encoding is percent-encoded (like `quote_plus`).
fn form_encode(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for byte in text.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(byte as char),
            b' ' => out.push('+'),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

/// The text a parameter value is sent as.
fn value_text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.str()?.to_string())
}

/// `key=value` pairs sorted by key, `None` values left out, joined with `&`.
#[pyfunction]
fn encode_query(params: &Bound<'_, PyDict>) -> PyResult<String> {
    let mut pairs: Vec<(String, String)> = Vec::with_capacity(params.len());
    for (key, value) in params.iter() {
        if value.is_none() {
            continue;
        }
        pairs.push((key.str()?.to_string(), value_text(&value)?));
    }
    pairs.sort();
    let encoded: Vec<String> = pairs
        .iter()
        .map(|(key, value)| format!("{}={}", form_encode(key), form_encode(value)))
        .collect();
    Ok(encoded.join("&"))
}

#[pymodule]
fn fetchkit_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encode_query, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
