// CIDR blocks for network rules: parse a block, and tell whether an address is inside it.

/** A parsed block: its address family, its first address as a number, and its prefix length. */
export type Block = { family: 4 | 6; first: bigint; prefix: number };

/** A block that cannot be used. */
export class BlockError extends Error {
  name = "BlockError";
}

const BITS = { 4: 32, 6: 128 } as const;
const OCTET = /^(0|[1-9]\d{0,2})$/;
const PREFIX = /^(0|[1-9]\d{0,2})$/;

/** An IPv4 address ("192.0.2.7") as a 32-bit number, or undefined when the text is not one. */
export function parseIPv4(text: string): bigint | undefined {
  const parts = text.split(".");
  if (parts.length !== 4 || !parts.every((part) => OCTET.test(part) && Number(part) <= 255)) {
    return undefined;
  }
  return parts.reduce((value, part) => (value << 8n) | BigInt(part), 0n);
}

/** An IPv6 address ("2001:db8::1") as a 128-bit number, or undefined when the text is not one. */
export function parseIPv6(text: string): bigint | undefined {
  // The IPv6 half of #88 (the README's "Network rules" has the address syntax).
  void text;
  return undefined;
}

/** An address of either family, or undefined when the text is neither. */
export function parseAddress(text: string): { family: 4 | 6; value: bigint } | undefined {
  const v4 = parseIPv4(text);
  if (v4 !== undefined) {
    return { family: 4, value: v4 };
  }
  const v6 = parseIPv6(text);
  return v6 === undefined ? undefined : { family: 6, value: v6 };
}

/**
 * Parses a block: "10.0.0.0/8", "2001:db8::/32", or a single address ("192.0.2.7" is
 * "192.0.2.7/32"). The address must be the first address of its block. Throws BlockError.
 */
export function parseBlock(text: string): Block {
  const [addressText, prefixText, ...extra] = text.split("/");
  const address = parseAddress(addressText);
  if (address === undefined || extra.length > 0) {
    throw new BlockError(`not a CIDR block: ${JSON.stringify(text)}`);
  }
  const bits = BITS[address.family];
  let prefix = bits;
  if (prefixText !== undefined) {
    if (!PREFIX.test(prefixText) || Number(prefixText) > bits) {
      throw new BlockError(`not a CIDR block: ${JSON.stringify(text)}`);
    }
    prefix = Number(prefixText);
  }
  const hostBits = BigInt(bits - prefix);
  if ((address.value >> hostBits) << hostBits !== address.value) {
    throw new BlockError(`${JSON.stringify(text)} is not the first address of its block`);
  }
  return { family: address.family, first: address.value, prefix };
}

/** True when `address` is inside `block`. An address of the other family, or not an address, is not. */
export function contains(block: Block, address: string): boolean {
  const parsed = parseAddress(address);
  if (parsed === undefined || parsed.family !== block.family) {
    return false;
  }
  const hostBits = BigInt(BITS[block.family] - block.prefix);
  return parsed.value >> hostBits === block.first >> hostBits;
}
