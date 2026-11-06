import { test } from "node:test";
import assert from "node:assert/strict";
import { BlockError, contains, parseBlock } from "../src/cidr.ts";

const inside = (block: string, address: string) => contains(parseBlock(block), address);

test("IPv4 blocks and single addresses", () => {
  assert.equal(inside("10.0.0.0/8", "10.200.3.4"), true);
  assert.equal(inside("10.0.0.0/8", "11.0.0.1"), false);
  assert.equal(inside("192.0.2.128/25", "192.0.2.200"), true);
  assert.equal(inside("192.0.2.128/25", "192.0.2.127"), false);
  assert.equal(inside("203.0.113.7", "203.0.113.7"), true);
  assert.equal(inside("203.0.113.7", "203.0.113.8"), false);
  assert.equal(inside("0.0.0.0/0", "198.51.100.1"), true);
});

test("malformed IPv4 blocks are refused", () => {
  for (const text of ["10.0.0/8", "10.0.0.256/32", "10.0.0.0/33", "010.0.0.0/8", "10.0.0.1/8", "10.0.0.0/", "10.0.0.0/08", "10.0.0.0/8/9", ""]) {
    assert.throws(() => parseBlock(text), BlockError, text);
  }
});

test("IPv6 blocks in full and compressed form", () => {
  assert.equal(inside("2001:db8::/32", "2001:db8:ffff:1::42"), true);
  assert.equal(inside("2001:db8::/32", "2001:db9::1"), false);
  assert.equal(inside("2001:0DB8:0000:0000:0000:0000:0000:0000/32", "2001:db8::1"), true);
  assert.equal(inside("fd00:a:b::/48", "fd00:a:b:c::1"), true);
  assert.equal(inside("fd00:a:b::/48", "fd00:a:c::1"), false);
  assert.equal(inside("::1", "0:0:0:0:0:0:0:1"), true);
  assert.equal(inside("::/0", "fe80::1"), true);
  assert.equal(inside("2001:db8::8000/113", "2001:db8::ffff"), true);
  assert.equal(inside("2001:db8::8000/113", "2001:db8::7fff"), false);
});

test("malformed IPv6 blocks are refused", () => {
  for (const text of [
    "2001:db8:::/32",
    "2001:db8::1::/64",
    "2001:db8:0:0:0:0:0:0:0/64",
    "2001:db8:12345::/32",
    "2001:db8::/129",
    "2001:db8::1/32",
    "2001:dg8::/32",
    ":2001:db8::/32",
    "2001:db8:/32",
  ]) {
    assert.throws(() => parseBlock(text), BlockError, text);
  }
});

test("an address is never inside a block of the other family", () => {
  assert.equal(inside("::/0", "10.0.0.1"), false);
  assert.equal(inside("0.0.0.0/0", "::1"), false);
  assert.equal(inside("10.0.0.0/8", "not-an-ip"), false);
  assert.equal(inside("2001:db8::/32", "2001:db8::g"), false);
});
