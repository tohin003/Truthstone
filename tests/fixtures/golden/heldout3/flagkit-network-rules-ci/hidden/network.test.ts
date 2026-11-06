// Network rules follow the README's address and block syntax for IPv6 as for IPv4, end to end.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { BlockError, contains, parseBlock } from "../src/cidr.ts";
import { main } from "../src/cli.ts";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const inside = (block: string, address: string) => contains(parseBlock(block), address);
const env = {};

test("IPv6 addresses in every documented spelling", () => {
  for (const spelling of ["2001:db8::1", "2001:0db8:0000:0000:0000:0000:0000:0001", "2001:DB8::1", "2001:db8:0::0:1", "2001:db8::0:0:1"]) {
    assert.equal(inside("2001:db8:0:0:0:0:0:1/128", spelling), true, spelling);
  }
  assert.equal(inside("::/128", "0:0:0:0:0:0:0:0"), true);
  assert.equal(inside("::/128", "::1"), false);
  assert.equal(inside("1::/16", "1:ffff::"), true);
  assert.equal(inside("1:2:3:4:5:6:7::/112", "1:2:3:4:5:6:7:abcd"), true);
  assert.equal(inside("1:2:3:4:5:6:7::/112", "1:2:3:4:5:6:8:0"), false);
});

test("IPv6 prefixes are compared bit by bit", () => {
  assert.equal(inside("2001:db8:abcd:1200::/56", "2001:db8:abcd:12ff:ffff::1"), true);
  assert.equal(inside("2001:db8:abcd:1200::/56", "2001:db8:abcd:1300::"), false);
  assert.equal(inside("2001:db8::/127", "2001:db8::1"), true);
  assert.equal(inside("2001:db8::/127", "2001:db8::2"), false);
  assert.equal(inside("fe80::/10", "febf:ffff::1"), true);
  assert.equal(inside("fe80::/10", "fec0::1"), false);
  assert.equal(inside("8000::/1", "ffff::"), true);
  assert.equal(inside("8000::/1", "7fff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"), false);
});

test("malformed IPv6 blocks and addresses are refused", () => {
  for (const text of [
    "1:2:3:4:5:6:7:8::/64",
    "1::2::3",
    ":::",
    "::1:/128",
    "1:2:3:4:5:6:7/112",
    "2001:db8::/0129",
    "2001:db8::/-1",
    "2001:db8::/12.5",
    "2001:db8:: /32",
    "g::/16",
    "::1/128/1",
    "2001:db8::8000/112",
  ]) {
    assert.throws(() => parseBlock(text), BlockError, text);
  }
  for (const address of ["2001:db8::1::", "2001:db8:::1", "12345::", "1:2:3:4:5:6:7", "::g", ""]) {
    assert.equal(inside("::/0", address), false, address);
  }
});

test("IPv4 is unchanged", () => {
  assert.equal(inside("172.16.0.0/12", "172.31.255.255"), true);
  assert.equal(inside("172.16.0.0/12", "172.32.0.0"), false);
  assert.equal(inside("198.51.100.0/31", "198.51.100.1"), true);
  for (const text of ["256.0.0.0/8", "1.2.3/24", "1.2.3.4.5/32", "01.2.3.4", "172.16.0.0/012", "172.17.0.0/12"]) {
    assert.throws(() => parseBlock(text), BlockError, text);
  }
});

test("an address is never inside a block of the other family", () => {
  assert.equal(inside("::/0", "192.0.2.1"), false);
  assert.equal(inside("0.0.0.0/0", "2001:db8::1"), false);
});

test("configs take IPv6 blocks and refuse malformed ones, naming the rule", () => {
  const values = ["2001:db8:4f00::/40", "10.20.0.0/16", "::1"];
  const config = parseConfig({ flags: { vpn: { enabled: true, rules: [{ type: "network", values }] } } });
  assert.deepEqual(config.flags.get("vpn")?.rules, [{ type: "network", values }]);
  for (const bad of ["2001:db8:4f00::/39", "2001:db8::/129", "2001::db8::/32"]) {
    assert.throws(
      () => parseConfig({ flags: { vpn: { enabled: true, rules: [{ type: "network", values: [bad] }] } } }),
      (error: unknown) => error instanceof ConfigError && /flag "vpn": rule 1: "values" must be a non-empty list of CIDR blocks/.test(error.message),
      bad,
    );
  }
});

test("network rules decide for IPv6 clients, end to end", () => {
  const path = fileURLToPath(new URL("./fixtures/vpn.json", import.meta.url));
  const config = loadConfig(path);
  assert.equal(evaluate(config, "staff-tools", { ip: "2001:db8:4fff::1" }, { env }).reason, "network:hit");
  assert.equal(evaluate(config, "staff-tools", { ip: "2001:db8:5000::1" }, { env }).reason, "no-match");
  assert.equal(evaluate(config, "staff-tools", { ip: "10.20.255.1" }, { env }).reason, "network:hit");
  assert.equal(evaluate(config, "staff-tools", { userId: "qa-anna", ip: "garbage" }, { env }).reason, "allowlist:hit");
  let stdout = "";
  const status = main(["eval", path, "staff-tools", "--ip", "2001:db8:4f00::7"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.equal(stdout, "on (network:hit)\n");
});
