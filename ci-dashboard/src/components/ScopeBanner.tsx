import type { FilteredData } from '../lib/filters';
import { PRESET_LABEL } from '../lib/filters';
import { useAppState } from '../state/AppState';
import { service } from '../state/useData';
import { fmtInt } from '../lib/format';
import { MIN_TRANSCRIPTION_CONFIDENCE } from '../config';

const d2 = (d: Date) => d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

/** Every page states its period, comparison period, and denominators. */
export function scopeNote(d: FilteredData, preset: keyof typeof PRESET_LABEL): string {
  const w = d.windows;
  return `${PRESET_LABEL[preset]} (${d2(w.currentStart)} – ${d2(w.currentEnd)}) vs comparison (${d2(w.prevStart)} – ${d2(w.prevEnd)}) · ${fmtInt(d.analysed.length)} analysed of ${fmtInt(d.current.length)} total calls`;
}

export function ScopeBanner({ d }: { d: FilteredData }) {
  const { filters } = useAppState();
  // With a single-window snapshot there is no prior period to compare against,
  // so say it once per page rather than leaving every delta reading
  // "no prior data" with no explanation.
  if (!service.isMock && d.previous.length === 0 && d.current.length > 0) {
    return (
      <div className="low-conf-note">
        No calls exist in the comparison window — this dataset covers a single
        24-day period, so period-over-period deltas show “no prior data”.
        {d.excludedLowConfidence > 0 && ` ${fmtInt(d.excludedLowConfidence)} call(s) also excluded for low transcription confidence.`}
      </div>
    );
  }
  if (filters.includeLowConfidence && d.excludedLowConfidence > 0) {
    return (
      <div className="low-conf-note">
        Including {fmtInt(d.excludedLowConfidence)} low-confidence transcript(s) (&lt;{MIN_TRANSCRIPTION_CONFIDENCE * 100}% ASR confidence) in aggregates — treat totals as indicative.
      </div>
    );
  }
  if (d.excludedLowConfidence > 0) {
    return (
      <div className="low-conf-note">
        {fmtInt(d.excludedLowConfidence)} call(s) excluded from aggregates due to transcription confidence below {MIN_TRANSCRIPTION_CONFIDENCE * 100}%. Toggle “Include low-confidence transcripts” in filters to view them.
      </div>
    );
  }
  return null;
}
