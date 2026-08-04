export interface PageHelp {
  title: string;
  purpose: string;
  numbers: string[];
  actions: string[];
}

export const PAGE_HELP: Record<string, PageHelp> = {
  '/': {
    title: 'Executive Overview',
    purpose: 'A quick summary of call volume, customer mood, buying interest, agent performance, follow-ups and risks.',
    numbers: ['Large cards are totals for the selected period.', 'Percentages use the denominator written below the number.', 'Arrows compare the selected period with the previous equal-length period.'],
    actions: ['Click a card or chart item to open the calls behind it.', 'Use the filters at the top to narrow every number on the page.'],
  },
  '/voice': {
    title: 'Customer Voice & Sentiment',
    purpose: 'Shows what customers liked, disliked, requested and felt during calls.',
    numbers: ['Sentiment percentages are shares of analysed calls.', 'Theme counts show how many calls mentioned that theme, counted once per call.', 'A shift shows whether customer sentiment improved or worsened during the call.'],
    actions: ['Click a theme or chart section to see its supporting calls and transcripts.'],
  },
  '/faqs': {
    title: 'FAQs & Knowledge Gaps',
    purpose: 'Groups customer questions and shows whether agents answered them fully, partly or not at all.',
    numbers: ['An occurrence means one question in one call; repeats of the same standardised question in that call count once.', 'Answered, partial and unanswered numbers are call-level occurrences.', 'Emerging means the question appeared more often than in the comparison period.'],
    actions: ['Click a question to see only calls containing that exact question.', 'Click an answered, partial or unanswered badge to see only calls with that result.'],
  },
  '/regions': {
    title: 'Regional Intelligence',
    purpose: 'Compares customer outcomes across CRM regions, states and cities.',
    numbers: ['Heatmap values with % signs are rates, not call counts.', 'Darker cells mean a higher percentage.', 'The warning symbol means the sample is below 25 analysed calls, so treat it as an observation rather than a firm trend.'],
    actions: ['Click a cell or region row to open the calls used for it.', 'Switch between Region, State and City using the tabs.'],
  },
  '/sales': {
    title: 'Sales & Objections',
    purpose: 'Shows buying readiness, customer objections, competitor mentions and sales outcomes.',
    numbers: ['Readiness and objection counts are based on analysed transcripts.', 'Resolved, partial and unresolved describe how the objection ended.', 'Orders and opportunities come from CRM fields, not AI guesses.'],
    actions: ['Click an objection, stage or chart item to see the matching calls.'],
  },
  '/agents': {
    title: 'Agent Quality',
    purpose: 'Compares agent call quality and highlights coaching opportunities.',
    numbers: ['Scores are averages from applicable call-quality dimensions.', 'A missing score means there was not enough evidence to assess it.', 'Low-sample agents are marked because a few calls can create extreme percentages.'],
    actions: ['Click an agent row to see the calls included in their score.'],
  },
  '/actions': {
    title: 'Next-Action Tracker',
    purpose: 'Lists follow-ups and commitments extracted from calls.',
    numbers: ['Pending, overdue and completed are action counts, not call counts.', 'Due dates are used only when a date was stated or assigned.', 'SLA status shows whether the follow-up is on time.'],
    actions: ['Click a call to inspect the evidence behind an action.', 'Status changes in the current static dashboard are temporary and reset on refresh.'],
  },
  '/calls': {
    title: 'Call Explorer',
    purpose: 'Shows the individual calls behind all dashboard totals and lets you inspect their evidence.',
    numbers: ['Calls match the selected period and active filters.', 'Analysed calls exclude non-meaningful and low-confidence transcripts unless you include them.', 'AI confidence describes extraction confidence; it is not customer sentiment.'],
    actions: ['Click a call row to open its transcript, summary, evidence, FAQs, objections and actions.', 'Use Reset at the top if a previous drill-down is still filtering the list.'],
  },
  '/alerts': {
    title: 'Alerts & Escalations',
    purpose: 'Collects urgent risks, overdue commitments, complaints and compliance concerns.',
    numbers: ['Severity describes urgency.', 'Open, acknowledged and resolved describe the alert workflow.', 'Counts may include several alerts from one call.'],
    actions: ['Click an alert to inspect the source call and transcript evidence.'],
  },
  '/data': {
    title: 'Data Quality & Configuration',
    purpose: 'Explains where the data came from, what is real, what is incomplete and what was excluded.',
    numbers: ['Green means supported by real source data.', 'Amber means real data with a declared limitation.', 'Red means demo data without a real source.', 'Coverage numbers explain why analysed-call totals can be smaller than total calls.'],
    actions: ['Use this page when a metric looks surprising or you need to understand a limitation.'],
  },
};
