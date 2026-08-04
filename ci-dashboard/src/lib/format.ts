export const fmtInt = (n: number) => n.toLocaleString('en-IN');

export const fmtPct = (num: number, den: number, dp = 0) =>
  den === 0 ? '—' : `${((num / den) * 100).toFixed(dp)}%`;

export const pctVal = (num: number, den: number) => (den === 0 ? 0 : (num / den) * 100);

/** Indian currency, compact: ₹4.5 L / ₹1.2 Cr */
export function fmtINR(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return `₹${v.toLocaleString('en-IN')}`;
}

export function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export const fmtTimestamp = (sec: number) => fmtDuration(Math.max(0, Math.round(sec)));

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

export const fmtDelta = (cur: number, prev: number): { text: string; dir: 'up' | 'down' | 'flat' } => {
  if (prev === 0) return { text: 'no prior data', dir: 'flat' };
  const d = ((cur - prev) / Math.abs(prev)) * 100;
  if (Math.abs(d) < 0.5) return { text: '±0%', dir: 'flat' };
  return { text: `${d > 0 ? '+' : ''}${d.toFixed(0)}%`, dir: d > 0 ? 'up' : 'down' };
};

export const sentimentScoreLabel = (v: number) =>
  v > 0.15 ? 'Positive' : v < -0.15 ? 'Negative' : 'Neutral';

/**
 * "Vanshika Bhardwaj" → "Vanshika B."  ·  "Pallavi" → "Pallavi"
 * Several Sunrooof agents are recorded in Zoho with a single name, so the
 * surname initial has to be optional rather than assumed.
 */
export const shortName = (name: string): string => {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'Unknown';
  if (parts.length === 1) return parts[0];
  return `${parts[0]} ${parts[1][0]}.`;
};
