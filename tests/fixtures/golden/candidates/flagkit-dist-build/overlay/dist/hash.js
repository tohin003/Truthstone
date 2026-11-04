// Generated from src/hash.ts by scripts/build.ts. Do not edit: run `npm run build`.
// FNV-1a hashing and the 0-99 rollout buckets that percentage rules compare against.
// This file is also compiled into the embedded SDK, whose runtime has no Node or Web APIs
// (no Buffer, no TextEncoder): keep it plain JavaScript.

const FNV_OFFSET_BASIS = 0x811c9dc5;
const FNV_PRIME = 0x01000193;

/** 32-bit FNV-1a over the string's UTF-16 code units, as an unsigned integer. */
export function fnv1a32(text        )         {
  let hash = FNV_OFFSET_BASIS;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, FNV_PRIME) >>> 0;
  }
  return hash >>> 0;
}

/**
 * The user's bucket for a flag, 0-99: fnv1a32(`${flagKey}:${userId}`) % 100. A
 * percentage rule of N % includes exactly the users whose bucket is below N. Buckets are
 * part of the contract with analytics: they must never change for an existing user.
 */
export function bucket(flagKey        , userId        )         {
  return fnv1a32(`${flagKey}:${userId}`) % 100;
}
