import type { ComparisonRow } from '../../core/mailbox-types';
export type Status = 'matched' | 'discrepancy' | 'unknown' | 'external' | 'reply' | 'unobserved';
export const statuses: Record<Status, { label: string; symbol: string }> = {
  matched: { label: 'Matched', symbol: '✓' },
  discrepancy: { label: 'Discrepancy', symbol: '!' },
  unknown: { label: 'Unknown outcome', symbol: '?' },
  external: { label: 'External only', symbol: '↗' },
  reply: { label: 'Reply evidence', symbol: '↩' },
  unobserved: { label: 'Not established', symbol: '·' },
};
// Presentation of Core findings only; never infer a match from content or elapsed time.
export function statusOf(row: ComparisonRow): Status {
  const codes = row.findings.map(f => f.finding);
  if (codes.includes('external_schedule_changed')) return 'discrepancy';
  if (row.local && ['unknown', 'placement_unknown', 'cancel_unknown', 'in_progress'].includes(row.local.state)) return 'unknown';
  if (codes.some(c => ['matched_unresolved_attempt', 'ambiguous_observation', 'ambiguous_local_match', 'schedule_evidence_missing', 'observation_unavailable'].includes(c))) return 'unknown';
  if (codes.some(c => ['matched_sent_record', 'external_schedule_still_active', 'schedule_observed_sent'].includes(c))) return 'matched';
  if (row.observed?.direction === 'inbound' || row.local?.kind === 'reply_association') return 'reply';
  if (!row.local && row.observed) return 'external';
  return 'unobserved';
}
export function kindOf(row: ComparisonRow) {
  if (row.observed?.direction === 'inbound' || row.local?.kind === 'reply_association') return 'replies';
  if (row.local?.kind === 'external_schedule' || row.observed?.status === 'scheduled') return 'schedules';
  if (row.local?.kind === 'sent_record' || row.observed?.status === 'sent') return 'sent';
  return 'other';
}
