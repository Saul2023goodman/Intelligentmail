# SmartMail Recognition Hard Cases

These are deliberately difficult recognition samples selected from Google Drive. They are intended to stress deterministic classification/association logic rather than provide only clean happy-path examples.

## Expected handling

1. `Ping Tan.docx`
   - Actual type: outreach email draft.
   - Hard case: filename is only a person name; no institution, student, or "email/draft" token in filename.
   - Recognition goal: infer draft from document structure/content, identify supervisor from salutation/body, and associate student from sender self-introduction rather than filename.

2. `Yixuan Yuan.docx`
   - Actual type: outreach email draft.
   - Hard case: same filename pattern as above; useful for ensuring the rule generalizes rather than memorizing one name.
   - Recognition goal: content-based draft classification and student/supervisor association.

3. `youyue 邮件维护日志.docx`
   - Actual type: maintenance/log/reference document, NOT a single outreach draft.
   - Hard case: contains many supervisor names, institutions, links, and email-related language, so naive keyword rules may classify it as a draft or master list.
   - Recognition goal: reject as a single-send draft; retain as reference/unsupported source unless a dedicated log type exists.

4. `Qian-CV.docx`
   - Actual type: CV, but it is a scholar/professor CV rather than the applicant/student CV used as an attachment.
   - Hard case: filename says CV and content has education/research/publications, so format-only logic will call it a student attachment.
   - Recognition goal: distinguish document type from role/identity; do not automatically bind every CV to the current student.

5. `未命名电子表格.xlsx`
   - Actual type: unrelated bilingual legal-language/collocation research spreadsheet, NOT a SmartMail master list.
   - Hard case: generic spreadsheet filename gives no semantic clue.
   - Recognition goal: reject master-list classification based solely on `.xlsx`; require expected structural/header evidence.

6. `刘帅辰同学2028-2029硕士申请时间规划.docx`
7. `刘帅辰同学2028-2029硕士申请时间规划（原版备份）.docx`
   - Actual type: student planning/reference documents, NOT email drafts and NOT sendable attachments by default.
   - Hard case: same student identity, near-duplicate/version pair, application/supervisor/contact terminology may overlap with outreach content.
   - Recognition goal: detect non-draft planning document; avoid creating tasks from it; recognize version/duplicate relationship without silently replacing one source.


8. `焦俊豪_网易邮箱插件导入_全量56人_v2(1).csv`
   - Actual type: import-ready bulk outreach table with 56 rows.
   - Hard case: already contains recipient, subject, body, attachment, and scheduled time; it is closer to an executable batch source than a generic supervisor/master list.
   - Recognition goal: classify as structured outreach import, create/associate multiple tasks without collapsing it into one document-level task, and preserve explicit schedule/attachment fields.

9. `sample2.docx`
   - Actual type: multi-draft outreach bundle containing many supervisor-specific email drafts for the same student.
   - Hard case: one Word document contains many complete emails, supervisors, institutions, subjects, notes, and email addresses.
   - Recognition goal: do not classify the whole document as one draft; segment or flag it as a multi-draft bundle, preserve student identity across entries, and associate each supervisor-specific section separately when supported.

10. `2027_新加坡教育心理学硕士项目补充(1).xlsx`
   - Actual type: graduate-program research/comparison workbook, NOT an outreach master list.
   - Hard case: structured spreadsheet with schools, programs, requirements, deadlines, URLs, and multiple sheets can superficially resemble an operational master list.
   - Recognition goal: reject outreach/master-list classification unless required recipient/task fields are present; classify as planning/reference data or unsupported source rather than generating send tasks.

## What this set should expose

- filename-only classification
- extension-only classification
- role confusion (student vs supervisor/person mentioned in source)
- one-document-many-people ambiguity
- content that is email-related but not an email draft
- generic/unnamed files
- near-duplicate/versioned sources
- false-positive master-list detection
- false-positive attachment association
- multi-draft bundle segmentation
- structured batch-import recognition
- planning spreadsheet vs outreach master-list discrimination

For deterministic recognition, prefer explicit structural evidence and confidence/exception states over guessing when identity or source role is ambiguous.
