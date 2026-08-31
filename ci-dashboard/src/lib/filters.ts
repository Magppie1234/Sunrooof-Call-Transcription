import type { CallRecord } from '../types/domain';
import { EMPLOYEES } from '../data/taxonomy';
import { MIN_TRANSCRIPTION_CONFIDENCE } from '../config';

export type DatePreset = '7d' | '30d' | '90d' | 'custom';

/** All dimension filters use '' to mean "all". */
export interface FilterState {
  preset: DatePreset;
  /** YYYY-MM-DD, inclusive. Only read when preset === 'custom'. */
  customStart: string;
  customEnd: string;
  region: string;
  state: string;
  city: string;
  team: string;
  employee: string;
  product: string;
  direction: string;
  language: string;
  sentiment: string;
  outcome: string;
  leadSource: string;
  campaign: string;
  intent: string;
  customerType: string;
  faqCategory: string;
  faqQuestion: string;
  faqStatus: string;
  faqSentimentAfter: string;
  objection: string;
  actionStatus: string;
  compliance: string; // 'flagged' | ''
  includeLowConfidence: boolean;
  search: string;
}

export const DEFAULT_FILTERS: FilterState = {
  preset: '30d', customStart: '', customEnd: '', region: '', state: '', city: '', team: '', employee: '', product: '',
  direction: '', language: '', sentiment: '', outcome: '', leadSource: '', campaign: '',
  intent: '', customerType: '', faqCategory: '', faqQuestion: '', faqStatus: '', faqSentimentAfter: '', objection: '', actionStatus: '',
  compliance: '', includeLowConfidence: false, search: '',
};

/**
 * Every key matchesDims() narrows on. All are strings where '' means "all".
 *
 * The filter bar derives both its active count and its chip row from this list,
 * so a key matchesDims reads but this list omits becomes a filter the user can
 * neither see nor clear — which is how a drill-down on city, outcome or search
 * could silently hold the whole dashboard down to a fraction of its calls with
 * nothing on screen to say why. Keep this in step with matchesDims().
 */
export const DIMENSION_LABELS = {
  region: 'Region', state: 'State', city: 'City', team: 'Team', employee: 'Employee',
  product: 'Product', direction: 'Direction', language: 'Language', sentiment: 'Sentiment',
  outcome: 'Outcome', leadSource: 'Lead source', campaign: 'Campaign', intent: 'Purchase readiness',
  customerType: 'Customer type', faqCategory: 'FAQ category', faqQuestion: 'FAQ',
  faqStatus: 'FAQ status', faqSentimentAfter: 'Sentiment after answer', objection: 'Objection',
  actionStatus: 'Action status', compliance: 'Compliance', search: 'Search',
} as const satisfies Partial<Record<keyof FilterState, string>>;

export type DimensionKey = keyof typeof DIMENSION_LABELS;
export const DIMENSION_KEYS = Object.keys(DIMENSION_LABELS) as DimensionKey[];

// 'custom' has no fixed day-count — the 0 is a placeholder never read (see
// periodWindows below, which branches to customStart/customEnd instead).
export const PRESET_DAYS: Record<DatePreset, number> = { '7d': 7, '30d': 30, '90d': 90, custom: 0 };
export const PRESET_LABEL: Record<DatePreset, string> = { '7d': 'Last 7 days', '30d': 'Last 30 days', '90d': 'Last 90 days', custom: 'Custom range' };

export interface PeriodWindows {
  currentStart: Date;
  currentEnd: Date;
  prevStart: Date;
  prevEnd: Date;
}

/**
 * Takes the whole FilterState (not just the preset) because 'custom' needs
 * customStart/customEnd. For a rolling preset, `now` is the window's end —
 * for 'custom' it's ignored and the picked dates are used directly, with the
 * comparison window set to the same-length span immediately before it.
 */
export function periodWindows(f: Pick<FilterState, 'preset' | 'customStart' | 'customEnd'>, now = new Date()): PeriodWindows {
  if (f.preset === 'custom' && f.customStart && f.customEnd) {
    const currentStart = new Date(`${f.customStart}T00:00:00`);
    // End date is inclusive of the whole day the user picked.
    const currentEnd = new Date(new Date(`${f.customEnd}T00:00:00`).getTime() + 86400_000);
    const spanMs = currentEnd.getTime() - currentStart.getTime();
    const prevEnd = currentStart;
    const prevStart = new Date(currentStart.getTime() - spanMs);
    return { currentStart, currentEnd, prevStart, prevEnd };
  }
  const days = PRESET_DAYS[f.preset] || 30;
  const currentEnd = now;
  const currentStart = new Date(now.getTime() - days * 86400_000);
  const prevEnd = currentStart;
  const prevStart = new Date(currentStart.getTime() - days * 86400_000);
  return { currentStart, currentEnd, prevStart, prevEnd };
}

const empTeam = (id: string) => EMPLOYEES.find((e) => e.id === id)?.team ?? '';

function matchesDims(c: CallRecord, f: FilterState): boolean {
  if (f.region && c.region !== f.region) return false;
  if (f.state && c.state !== f.state) return false;
  if (f.city && c.city !== f.city) return false;
  if (f.team && empTeam(c.employeeId) !== f.team) return false;
  if (f.employee && c.employeeId !== f.employee) return false;
  if (f.product && c.productSeries !== f.product) return false;
  if (f.direction && c.direction !== f.direction) return false;
  if (f.language && c.language !== f.language) return false;
  if (f.sentiment && (c.sentiment?.overall ?? 'not_analysed') !== f.sentiment) return false;
  if (f.outcome && c.outcome !== f.outcome) return false;
  if (f.leadSource && c.leadSource !== f.leadSource) return false;
  if (f.campaign && c.campaign !== f.campaign) return false;
  if (f.intent && c.intent !== f.intent) return false;
  if (f.customerType && c.customerType !== f.customerType) return false;
  if (f.faqCategory || f.faqQuestion || f.faqStatus || f.faqSentimentAfter) {
    const matchesFaq = c.faqs.some((q) =>
      (!f.faqCategory || q.category === f.faqCategory) &&
      (!f.faqQuestion || q.standardized === f.faqQuestion) &&
      (!f.faqStatus || q.status === f.faqStatus) &&
      (!f.faqSentimentAfter || q.sentimentAfter === f.faqSentimentAfter));
    if (!matchesFaq) return false;
  }
  if (f.objection && !c.objections.some((o) => o.type === f.objection)) return false;
  if (f.actionStatus && !c.actions.some((a) => a.slaStatus === f.actionStatus || a.status === f.actionStatus)) return false;
  if (f.compliance === 'flagged' && c.complianceFlags.length === 0) return false;
  if (f.search) {
    const q = f.search.toLowerCase();
    const hay = `${c.id} ${c.customerName} ${c.summary} ${c.topics.join(' ')}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

export interface FilteredData {
  /** All calls in current window matching dimensions (incl. failed/short calls). */
  current: CallRecord[];
  /** Prior comparison window, same dimensions. */
  previous: CallRecord[];
  /** Analysed = meaningful + transcribed + confidence above threshold: the denominator for insight metrics. */
  analysed: CallRecord[];
  analysedPrev: CallRecord[];
  /** Calls excluded from aggregates due to low transcription confidence. */
  excludedLowConfidence: number;
  windows: PeriodWindows;
}

export const isAnalysable = (c: CallRecord, includeLowConfidence: boolean) =>
  c.meaningful && c.transcribed && c.sentiment !== null &&
  (includeLowConfidence || c.transcriptionConfidence >= MIN_TRANSCRIPTION_CONFIDENCE);

export function applyFilters(calls: CallRecord[], f: FilterState, now = new Date()): FilteredData {
  const windows = periodWindows(f, now);
  const inWindow = (c: CallRecord, s: Date, e: Date) => {
    const t = new Date(c.dateTime).getTime();
    return t >= s.getTime() && t < e.getTime();
  };
  const current = calls.filter((c) => inWindow(c, windows.currentStart, windows.currentEnd) && matchesDims(c, f));
  const previous = calls.filter((c) => inWindow(c, windows.prevStart, windows.prevEnd) && matchesDims(c, f));
  const analysed = current.filter((c) => isAnalysable(c, f.includeLowConfidence));
  const analysedPrev = previous.filter((c) => isAnalysable(c, f.includeLowConfidence));
  const excludedLowConfidence = current.filter(
    (c) => c.meaningful && c.transcribed && c.transcriptionConfidence < MIN_TRANSCRIPTION_CONFIDENCE,
  ).length;
  return { current, previous, analysed, analysedPrev, excludedLowConfidence, windows };
}
