// Property tests for bucketing: flagkit must bucket exactly like the Go service, which hashes UTF-8 bytes.
import { test } from "node:test";
import assert from "node:assert/strict";
import fc from "fast-check";
import { bucket, fnv1a32 } from "../src/hash.ts";

/** FNV-1a over the UTF-8 bytes, the way the Go service computes it. */
function goFnv1a32(text: string): number {
  let hash = 0x811c9dc5;
  for (const byte of Buffer.from(text, "utf8")) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

test("fnv1a32 hashes the UTF-8 bytes of any string", () => {
  fc.assert(fc.property(fc.fullUnicodeString(), (text) => fnv1a32(text) === goFnv1a32(text)));
});

test("buckets match the Go service for any flag and user", () => {
  fc.assert(
    fc.property(fc.string({ minLength: 1 }), fc.fullUnicodeString({ minLength: 1 }), (flag, user) => {
      assert.equal(bucket(flag, user), goFnv1a32(`${flag}:${user}`) % 100);
    }),
  );
});
