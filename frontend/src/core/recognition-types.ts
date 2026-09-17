// Contract for smartmail.recognition deterministic source classification.
// Core owns every type decision; the UI may only revise the effective type.

export type RecognitionTypeId =
  | "outreach_draft"
  | "multi_draft_bundle"
  | "applicant_cv"
  | "scholar_cv"
  | "supervisor_master"
  | "tracking_sheet"
  | "program_reference"
  | "bulk_import"
  | "planning_document"
  | "maintenance_log"
  | "unrelated"
  | "bundle"
  | "unknown"
  | "ambiguous";

export type RecognitionConfidence = "high" | "medium" | "low";

export type RecognitionSegment = {
  index: number;
  supervisor: string;
  salutation_name: string;
  title: string;
  institution: string;
  subject: string;
  signer: string;
  emails: string[];
};

export type RecognitionResult = {
  name: string;
  format: string;
  type: RecognitionTypeId;
  label: string;
  confidence: RecognitionConfidence;
  actionable: boolean;
  reasons: string[];
  cautions: string[];
  evidence: Record<string, unknown>;
  identities: Record<string, unknown>;
  segments: RecognitionSegment[];
  alternatives: { type: string; score: number }[];
  sha256: string;
  members?: RecognitionResult[];
};

export type RecognitionRelation = {
  a: string;
  b: string;
  relation: "exact_duplicate" | "near_duplicate";
  similarity: number;
  containment?: number;
  basis: string[];
};

export type RecognitionCollection = {
  sources: RecognitionResult[];
  relations: RecognitionRelation[];
};

// Persisted per-source annotation returned by the intake workspace.
export type SourceRecognitionAnnotation = {
  type: RecognitionTypeId;
  recognized_type: RecognitionTypeId;
  confidence: RecognitionConfidence;
  revised: boolean;
  reasons: string[];
  cautions: string[];
  label: string;
  actionable: boolean;
  identities?: {
    student?: string;
    person?: string;
    cv_role?: string;
    contact_email?: string;
    subject?: string;
    addressee?: { name?: string; email?: string };
    row_count?: number;
    email_count?: number;
    recipient_count?: number;
    segment_count?: number;
  };
};
