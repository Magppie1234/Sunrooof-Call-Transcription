/** Core domain model — see docs/05-data-dictionary.md for field definitions. */

export type SentimentLabel = 'positive' | 'neutral' | 'negative';
export type CallDirection = 'inbound' | 'outbound';
export type AnswerStatus = 'answered' | 'partial' | 'unanswered';
export type Intensity = 'low' | 'medium' | 'high';
export type Resolution = 'resolved' | 'partial' | 'unresolved';
export type IntentLevel = 'high' | 'medium' | 'low' | 'none';
export type CustomerType = 'New lead' | 'Existing customer' | 'Dealer' | 'Architect/Designer';

export type CallOutcome =
  | 'Interested — follow-up'
  | 'Quotation requested'
  | 'Site visit scheduled'
  | 'Demo scheduled'
  | 'Order confirmed'
  | 'Callback requested'
  | 'Complaint raised'
  | 'Not interested'
  | 'No requirement'
  | 'Not connected';

export type FaqCategory =
  | 'Pricing & discounts'
  | 'Product features & benefits'
  | 'Product-series comparison'
  | 'Customisation'
  | 'Design, drawings & measurements'
  | 'Installation process'
  | 'Delivery & project timeline'
  | 'Warranty & AMC'
  | 'Service & complaint process'
  | 'Payment & finance'
  | 'Product quality'
  | 'Serviceable locations'
  | 'Competitor comparison'
  | 'Documents & process'
  | 'Availability'
  | 'Technical specifications';

export type ObjectionType =
  | 'Price / discount'
  | 'Budget'
  | 'Timing'
  | 'Product suitability'
  | 'Product quality'
  | 'Trust'
  | 'Installation'
  | 'Warranty / service'
  | 'Competitor preference'
  | 'Decision-maker unavailable'
  | 'Serviceability'
  | 'Payment terms'
  | 'Not interested';

export type ActionType =
  | 'Call back'
  | 'Send catalogue / brochure'
  | 'Share quotation'
  | 'Schedule meeting'
  | 'Schedule demonstration'
  | 'Arrange site visit'
  | 'Share design / drawings'
  | 'Arrange measurement'
  | 'Provide technical clarification'
  | 'Follow up on payment'
  | 'Escalate complaint'
  | 'Assign a specialist'
  | 'Nurture the customer'
  | 'Disqualify lead (needs approval)';

export type ActionStatus = 'pending' | 'approved' | 'in_progress' | 'completed' | 'rejected';
export type SlaStatus = 'on_track' | 'due_today' | 'overdue' | 'met' | 'breached';

export interface TranscriptSegment {
  t: number; // seconds from call start
  speaker: 'agent' | 'customer';
  text: string;
}

export interface FaqHit {
  category: FaqCategory;
  standardized: string;
  originalQuestion: string;
  status: AnswerStatus;
  responseTimeSec: number | null;
  sentimentAfter: SentimentLabel;
  escalationNeeded: boolean;
  t: number;
}

export interface ObjectionHit {
  type: ObjectionType;
  intensity: Intensity;
  /** Customer's own words — transcript evidence for the objection. */
  statement: string;
  employeeResponse: string;
  technique: string;
  resolution: Resolution;
  customerReaction: SentimentLabel;
  /** Seconds from call start, matched back to the diarised turn. Null when the
   *  quoted statement could not be located in the transcript. */
  t: number | null;
}

export interface NextAction {
  id: string;
  callId: string;
  customerName: string;
  action: ActionType;
  source: 'committed' | 'ai_recommended';
  committedBy: 'employee' | 'customer' | null;
  ownerEmployeeId: string;
  priority: 'P1' | 'P2' | 'P3';
  dueDate: string; // ISO
  channel: 'Call' | 'WhatsApp' | 'Email' | 'Visit';
  reason: string;
  transcriptRef: number | null; // segment timestamp
  status: ActionStatus;
  slaStatus: SlaStatus;
  crmTaskLinked: boolean;
}

export interface QualityScores {
  opening: number;
  discovery: number;
  solutionRelevance: number;
  faqHandling: number;
  objectionHandling: number;
  nextStepClarity: number;
  listening: number;
  professionalism: number;
  overall: number; // weighted, 0–100
  complianceFail: boolean;
  complianceNotes: string | null;
  scriptAdherence: number;
  coachingNote: string | null;
}

export interface TalkMetrics {
  agentTalkPct: number;
  interruptions: number;
  longestSilenceSec: number;
}

export interface SentimentData {
  opening: number; // −1..1, text-based
  mid: number;
  closing: number;
  overall: SentimentLabel;
  shift: number; // closing − opening
  emotions: string[]; // frustration, confusion, hesitation, urgency, trust, interest, satisfaction
  unresolvedNegative: boolean;
}

export interface PurchaseReadiness {
  score: number; // 0–100
  needFit: number;
  explicitIntent: number;
  timeline: number;
  nextStepCommitment: number;
  authority: number;
  budget: number;
  sentiment: number;
}

export interface CrmSignals {
  opportunityCreated: boolean;
  orderConfirmed: boolean;
  complaintOpen: boolean;
  revenueInfluenced: number | null; // ₹, only when verified in CRM
  verified: boolean;
}

export interface CallRecord {
  id: string;
  dateTime: string; // ISO
  direction: CallDirection;
  durationSec: number;
  customerId: string;
  customerName: string;
  customerType: CustomerType;
  employeeId: string;
  region: string;
  state: string;
  city: string;
  productSeries: string;
  language: string;
  leadSource: string;
  campaign: string;
  crmStage: string;
  outcome: CallOutcome;
  connected: boolean;
  meaningful: boolean; // connected AND > 60s AND customer spoke
  transcribed: boolean;
  transcriptionConfidence: number;
  diarizationReliable: boolean;
  sentiment: SentimentData | null;
  purchaseReadiness: PurchaseReadiness | null;
  intent: IntentLevel;
  customerNeed: string | null;
  budgetMentioned: string | null; // "Not mentioned" handled via null
  timelineMentioned: string | null;
  decisionMaker: 'yes' | 'no' | 'unknown';
  buyingSignals: string[];
  crossSell: string | null;
  discountRequested: boolean;
  competitorMentions: string[];
  topics: string[];
  appreciationThemes: string[];
  dissatisfactionThemes: string[];
  featureRequests: string[];
  expectations: string[];
  painPoints: string[];
  faqs: FaqHit[];
  objections: ObjectionHit[];
  quality: QualityScores | null;
  talk: TalkMetrics | null; // null when diarisation unreliable
  actions: NextAction[];
  commitments: string[];
  risks: string[];
  complianceFlags: string[];
  entities: { text: string; type: string }[];
  summary: string;
  transcript: TranscriptSegment[];
  crm: CrmSignals;
  hasRecording: boolean;
  /** Zoho phonebridge URL. Real-data only; play via the local audio proxy
   * (scripts/audio_proxy.mjs on :3000), which holds the session cookie
   * server-side — never fetch this URL directly from the browser. */
  recordingUrl?: string | null;
  /** Whether an AI-generated summary note has ever reached Zoho for this
   * call (bulk sync or the Update CRM button). Informational only — the
   * button always re-checks Zoho's live state before writing anything. */
  crmNoteSynced?: boolean;
  crmTranscriptSynced?: boolean;
  /** The call's full QA audit. Present only on a record returned by
   *  getCall() — the list payload omits it, because criteria and conduct are
   *  46 MB across the corpus and render one call at a time. Typed as unknown
   *  here so domain.ts stays free of the audit's shape; QaAuditPanel owns that
   *  type and narrows it at the point of use. */
  qaAudit?: unknown;
}

export type AlertSeverity = 'critical' | 'high' | 'medium';

export interface AlertItem {
  id: string;
  severity: AlertSeverity;
  type: string;
  customerName: string | null;
  callId: string | null;
  ownerEmployeeId: string | null;
  reason: string;
  evidence: string;
  recommended: string;
  deadline: string; // ISO
  status: 'open' | 'acknowledged' | 'resolved';
}

export interface Employee {
  id: string;
  name: string;
  team: string;
  manager: string;
  role: 'Sales Consultant' | 'Service Executive';
}
