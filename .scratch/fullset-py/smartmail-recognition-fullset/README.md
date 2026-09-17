# SmartMail Recognition Full Set

This package combines the earlier representative/classic recognition samples with the newer hard-case set.

## classic/
Baseline samples for validating normal recognition:
- master/supervisor list
- follow-up spreadsheet
- CV / attachment
- standard outreach drafts
- mixed Chinese/English naming patterns

## hardcases/
Adversarial and ambiguous samples for improving recognition robustness:
- person-name-only draft filenames
- one document containing many drafts
- maintenance/log documents that mention many supervisors but are not drafts
- CV-like documents that should not be bound as a student attachment automatically
- unnamed spreadsheets that are unrelated to outreach
- near-duplicate/versioned documents
- bulk structured outreach import CSV
- planning/reference spreadsheets that should not become outreach tasks

Recommended use:
1. Make the classic set pass first.
2. Run hardcases to expose false positives and weak association rules.
3. Prefer structural/content evidence over filename and extension heuristics.
4. Keep uncertain cases unresolved instead of forcing a match.
