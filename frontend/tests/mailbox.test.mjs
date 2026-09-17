import assert from 'node:assert/strict';
import { test } from 'node:test';
import { statusOf, kindOf } from '../src/pages/mailbox/presentation.ts';

const row = (finding, state = 'sent') => ({ local: { state, kind: 'sent_record' }, observed: { status: 'sent' }, findings: finding ? [{ finding }] : [] });
test('unknown attempts remain unknown even with linked Sent evidence', () => {
  assert.equal(statusOf(row('matched_unresolved_attempt', 'unknown')), 'unknown');
  assert.equal(statusOf(row('matched_sent_record')), 'matched');
  assert.equal(statusOf(row(null)), 'unobserved');
});
test('schedule discrepancy and missing evidence do not become matches', () => {
  assert.equal(statusOf(row('external_schedule_changed', 'externally_scheduled')), 'discrepancy');
  assert.equal(statusOf(row('schedule_evidence_missing', 'externally_scheduled')), 'unknown');
  assert.equal(statusOf(row('external_schedule_still_active', 'externally_scheduled')), 'matched');
});
test('external and inbound evidence stay distinct from local Sent records', () => {
  assert.equal(statusOf({ local: null, observed: { status: 'sent' }, findings: [] }), 'external');
  const reply = { local: null, observed: { direction: 'inbound', status: 'received' }, findings: [] };
  assert.equal(statusOf(reply), 'reply');
  assert.equal(kindOf(reply), 'replies');
});
