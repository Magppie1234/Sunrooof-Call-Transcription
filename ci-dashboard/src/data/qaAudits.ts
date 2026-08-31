/**
 * The Advanced QA audit set, as both data modes hand it over.
 *
 * `calls` is deliberately unknown[]: the per-audit shape is 24 fields with a
 * criterion tree under it, declared where it is read (pages/AdvancedQa.tsx and
 * components/QaAuditPanel.tsx) rather than duplicated into the service layer,
 * which passes it through untouched. This mirrors what the page already did
 * with the raw JSON import.
 *
 * THE SET IS 6,260 AUDITS, SEVEN MORE THAN THE 6,253-CALL DATASET.
 * Those seven are calls where Sarvam returned an empty transcript:
 * build_ci_dataset.py drops them, the audit pipeline's conversation gate
 * recorded them as no_contact / NOT_SCORED. Anything that reconciles this list
 * against the call list has to expect the difference rather than treat it as a
 * fault — the qa_audits table has no foreign key for exactly this reason.
 */
export interface QaAuditSet {
  generatedAt: string;
  corpusSize: number;
  auditedCount: number;
  model: string;
  scorecard: string;
  calls: unknown[];
}
