/* Domain model. Every enum value here is a canonical term from CONTEXT.md —
   the interface never invents status vocabulary, it renders the query edges. */

export type StageId =
  | 'verify'
  | 'blocked'
  | 'ready'
  | 'confirmed'
  | 'executing'
  | 'sent'
  | 'followup'

export type MessageStatus =
  | 'locally_planned'
  | 'externally_scheduled'
  | 'sent'
  | 'observed_failure'
  | 'unknown_outcome'

export type Readiness = 'blocked' | 'ready' | 'confirmed' | 'superseded'

export type DuplicateStatus =
  | 'unchecked'
  | 'no_duplicate_found'
  | 'duplicate_suspicion'
  | 'ambiguous_match'
  | 'repeat_execution'
  | 'linked_follow_up'

export type ReplyAssociation =
  | 'none'
  | 'associated'
  | 'ambiguous'
  | 'automatic'
  | 'dismissed'

export type FollowupEligibility =
  | 'due'
  | 'waiting'
  | 'ordinary_reply_received'
  | 'reply_review_required'
  | 'maximum_reached'
  | 'no_initial_send'
  | 'follow_up_open'
  | 'rule_not_configured'

export type LinkState =
  | 'connected'
  | 'needs_login'
  | 'wrong_mailbox'
  | 'bridge_unavailable'

export type PauseReason =
  | 'unknown_outcome'
  | 'auth_interrupted'
  | 'new_blocker'
  | 'confirmation_expired'
  | 'execution_failed'

export type BlockerKind =
  | 'recipient_conflict'
  | 'identity_unconfirmed'
  | 'subject_missing'
  | 'attachment_missing'
  | 'rewrite_required'

export interface Blocker {
  id: string
  kind: BlockerKind
  label: string
  action: string
  shortcut: string
}

export interface FolderCoverage {
  folder: string
  declared: number
  enumerated: number
  pages: number
  pagesTotal: number
}

/** "Complete within supported scope" is not "complete for the whole mailbox".
 *  Blind spots are always rendered next to the conclusion they qualify. */
export interface EvidenceCoverage {
  folders: FolderCoverage[]
  blindSpots: string[]
}

export interface Attachment {
  id: string
  name: string
  bytes: number
  sha: string
  state: 'confirmed' | 'advisory' | 'missing'
}

export interface Attempt {
  id: string
  phase: 'intent' | 'submission' | 'evidence'
  note: string
}

export interface SentRecord {
  id: string
  canonicalId: string
  sentAt: string
}

export interface VersionEntry {
  at: string
  text: string
}

export interface OutreachTask {
  id: string
  stage: StageId
  student: string
  supervisor: string
  supervisorAliases: string[]
  /** Deliberately absent from every list and card — it is an attribute of the
   *  supervisor with zero effect on the next action. Surfaced only on hover. */
  institution: string
  mailbox: string
  sender: string
  recipient: string
  action: 'initial_outreach' | 'follow_up'
  status: MessageStatus
  readiness: Readiness
  duplicate: DuplicateStatus
  coverage: EvidenceCoverage
  reply: ReplyAssociation
  followup: {
    eligibility: FollowupEligibility
    waitedDays: number
    intervalDays: number
    limit: number
    round: number
  }
  subject: string
  body: string
  attachments: Attachment[]
  blockers: Blocker[]
  plannedAt?: string
  revisedFrom?: string
  attempt?: Attempt
  sentRecord?: SentRecord
  versions: VersionEntry[]
  /** Only facts that change the next action. Empty = a silent card. */
  annotation?: string
}

export interface ExecutionPause {
  id: string
  attempt: string
  taskId: string
  reason: PauseReason
  reasonLabel: string
  fact: string
  prevented: string
  primary: string
  secondary?: string
}

export type RecordChannel =
  | 'observation'
  | 'execution'
  | 'preparation'
  | 'confirmation'
  | 'import'
  | 'reconciliation'
  | 'reply'

export interface RecordEntry {
  id: string
  at: string
  channel: RecordChannel
  text: string
  tone: 'neutral' | 'verified' | 'alarm' | 'unknown'
  link?: string
}

export interface Campaign {
  id: string
  name: string
  meta: string
}

export interface NavSection {
  id: string
  label: string
  canonical: string
  icon: string
  lights?: { label: string; value: number; tone: 'alarm' | 'amber' | 'cool' }[]
}

export interface MailboxLink {
  address: string
  state: LinkState
  student: string
  lastSync: string
  capabilities: {
    id: string
    label: string
    state: 'verified' | 'disabled' | 'roadmap'
  }[]
}
