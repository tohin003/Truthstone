import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket, fnv1a32 } from "../src/hash.ts";

// Expected values are FNV-1a over the UTF-8 bytes, computed independently of flagkit.

test("ASCII hashes and buckets are unchanged", () => {
  assert.equal(fnv1a32(""), 0x811c9dc5);
  assert.equal(fnv1a32("a"), 0xe40c292c);
  assert.equal(fnv1a32("foobar"), 0xbf9cf968);
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("new-checkout", "user-3"), 1);
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("two-byte characters hash as UTF-8", () => {
  assert.equal(fnv1a32("é"), 0x1e9de8c1);
  assert.equal(fnv1a32("Zoë"), 0xc2a2bddc);
});

test("CJK characters hash as UTF-8", () => {
  assert.equal(fnv1a32("李"), 0xd5bbd2e6);
  assert.equal(fnv1a32("ユーザー"), 0x03cde6fe);
});

test("emoji hash as their four UTF-8 bytes", () => {
  assert.equal(fnv1a32("😀"), 0x33a29608);
  assert.equal(fnv1a32("🦄"), 0x0c130832);
  assert.equal(fnv1a32("user-ß-😀"), 0x1700f657);
});

test("non-ASCII users land in the Go service's buckets", () => {
  assert.equal(bucket("new-checkout", "zoë"), 23);
  assert.equal(bucket("new-checkout", "李雷"), 4);
  assert.equal(bucket("search-v2", "ユーザー42"), 47);
  assert.equal(bucket("search-v2", "😀-fan"), 67);
  assert.equal(bucket("offline-cart", "🦄"), 2);
  assert.equal(bucket("dark-mode", "josé"), 97);
});

test("percentage rules use the UTF-8 buckets", () => {
  const config = parseConfig({
    flags: {
      "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 68 }] },
      "offline-cart": { enabled: true, rules: [{ type: "percentage", percent: 2 }] },
    },
  });
  assert.equal(evaluate(config, "search-v2", { userId: "😀-fan" }, { env: {} }).reason, "percentage:67<68");
  assert.deepEqual(evaluate(config, "offline-cart", { userId: "🦄" }, { env: {} }).trace.map((step) => step.reason), [
    "percentage:2>=2",
  ]);
});

test("hashing needs no TextEncoder or Buffer: the embedded SDK has neither", async () => {
  const globals = globalThis as Record<string, unknown>;
  const saved = { TextEncoder: globals.TextEncoder, Buffer: globals.Buffer };
  delete globals.TextEncoder;
  delete globals.Buffer;
  try {
    const fresh = (await import("../src/hash.ts?without-platform-apis")) as typeof import("../src/hash.ts");
    assert.equal(fresh.fnv1a32("user-ß-😀"), 0x1700f657);
    assert.equal(fresh.bucket("search-v2", "😀-fan"), 67);
  } finally {
    Object.assign(globals, saved);
  }
});
