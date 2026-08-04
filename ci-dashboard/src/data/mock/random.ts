/**
 * ⚠️ MOCK DATA MODULE — deterministic seeded PRNG so generated demo data is
 * stable across reloads. Never imported by production/live services.
 */
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type Rng = () => number;

export const pick = <T,>(rng: Rng, arr: readonly T[]): T => arr[Math.floor(rng() * arr.length)];

export const pickN = <T,>(rng: Rng, arr: readonly T[], n: number): T[] => {
  const copy = [...arr];
  const out: T[] = [];
  while (out.length < n && copy.length) {
    out.push(copy.splice(Math.floor(rng() * copy.length), 1)[0]);
  }
  return out;
};

export const int = (rng: Rng, min: number, max: number) => min + Math.floor(rng() * (max - min + 1));

export const chance = (rng: Rng, p: number) => rng() < p;

/** Weighted pick: entries of [value, weight]. */
export function weighted<T>(rng: Rng, entries: readonly (readonly [T, number])[]): T {
  const total = entries.reduce((s, [, w]) => s + w, 0);
  let r = rng() * total;
  for (const [v, w] of entries) {
    r -= w;
    if (r <= 0) return v;
  }
  return entries[entries.length - 1][0];
}

export const round = (v: number, dp = 2) => Math.round(v * 10 ** dp) / 10 ** dp;

export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
