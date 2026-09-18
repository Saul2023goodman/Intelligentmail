"""Deterministic source recognition rules.

The rule tests are fully self-contained (synthetic documents, workbooks and
CSV tables built from the *generalized* schemas -- letter moves, CV sections,
workflow headers, period headers, envelope columns -- never from private
sample bytes.  The supplied recognition corpus is exercised separately by the
opt-in fullset test gated on SMARTMAIL_RECOGNITION_FULLSET.
"""

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

from smartmail.recognition import (
    AMBIGUOUS,
    APPLICANT_CV,
    BULK_IMPORT,
    MAINTENANCE_LOG,
    MULTI_DRAFT_BUNDLE,
    OUTREACH_DRAFT,
    PLANNING_DOCUMENT,
    PROGRAM_REFERENCE,
    SCHOLAR_CV,
    SUPERVISOR_MASTER,
    TRACKING_SHEET,
    UNKNOWN,
    UNRELATED,
    data_field_hints,
    detect_delimiter,
    detect_relations,
    normalize_header,
    profile_column,
    recognize_bytes,
    recognize_collection,
    recognize_file,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(paragraphs):
    """Minimal .docx container carrying only word/document.xml."""
    import io
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
        for text in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def docx_file(directory, name, paragraphs):
    path = Path(directory) / name
    with zipfile.ZipFile(path, "w") as archive:
        body = "".join(
            f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
            for text in paragraphs)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
        archive.writestr("word/document.xml", xml)
    return path


def workbook_file(directory, name, sheets):
    path = Path(directory) / name
    workbook = Workbook()
    first = True
    for title, rows in sheets:
        worksheet = workbook.active if first else workbook.create_sheet(title)
        if first:
            worksheet.title = title
        for row in rows:
            worksheet.append(row)
        first = False
    workbook.save(path)
    workbook.close()
    return path


def csv_bytes(rows, delimiter=","):
    import io
    buffer = io.StringIO()
    import csv as csv_module
    writer = csv_module.writer(buffer, delimiter=delimiter)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def merged_workbook_file(directory, name, title, rows, merges):
    """A workbook whose listed column ranges are merged vertically."""
    path = Path(directory) / name
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = title
    for row in rows:
        worksheet.append(row)
    for first, last in merges:
        worksheet.merge_cells(f"{first}:{last}")
    workbook.save(path)
    workbook.close()
    return path


# Shared synthetic letter content: salutation, goodwill opener, explicit
# self-introduction and purpose, addressee-work reference, CV attachment,
# sign-off -- the interpersonal move schema, not a file-name pattern.
DRAFT_WITHOUT_ENVELOPE = [
    "Dear Professor Tan,",
    "I hope this email finds you well.",
    "I am Shen Hui, with a Master's degree in Industrial Design Engineering. "
    "I am preparing to apply for PhD programs for the Fall 2027 intake, and I am "
    "writing to express my interest in joining your research group.",
    "Your work on diffusion-based camera calibration offers a compelling approach "
    "to limited calibration data. I have attached my CV and would be happy to "
    "provide further information.",
    "Yours sincerely,",
    "Shen Hui",
]

DRAFT_WITH_ENVELOPE = [
    "Email: martin.roberts@example.edu",
    "Dear Mr. Roberts,",
    "I hope this email finds you well.",
    "I am Sipei Yao and I am writing to express my interest in a PhD position. "
    "I was drawn to your article on art and nature. I have attached my CV.",
    "Yours sincerely,",
    "Sipei Yao",
    "Research source: example record",
]

APPLICANT_CV_PARAGRAPHS = [
    "Test Student",
    "student@example.com | +86 138 0000 0000 | linkedin.com/in/test-student | Chengdu, China",
    "EDUCATION",
    "Example University", "Sep 2022 - May 2026", "Bachelor of Arts in Psychology",
    "RESEARCH EXPERIENCE",
    "Independent study on learning outcomes", "Sep 2025 - Present",
    "TECHNICAL SKILLS",
    "R, Python, regression and survey design",
    "LANGUAGES",
    "Mandarin Chinese (native); English (professional)",
]

SCHOLAR_CV_PARAGRAPHS = [
    "Pat Example",
    "pat@example.edu",
    "pat.example.com",
    "Google Scholar",
    "Academic Appointments",
    "Presidential Frontier Faculty Assistant Professor Sept 2025 - Present",
    "Department of Computer Science, Example University",
    "Education",
    "Ph.D., Computer Science Aug 2019 - May 2025",
    "Funding",
    "NIH Pending",
    "Point-of-care AI decision support. $988,734. PI.",
    "Assistive robots for bedside tasks. $627,499. PI.",
    "Teaching",
    "Introduction to Robotics, guest lecturer",
]


class LetterFamilyTests(unittest.TestCase):
    def test_envelope_layout_is_single_draft_with_identities(self):
        result = recognize_bytes("Western Sydney University_Martin Roberts.docx",
                                 docx_bytes(DRAFT_WITH_ENVELOPE))
        self.assertEqual(result["type"], OUTREACH_DRAFT)
        self.assertEqual(result["confidence"], "high")
        self.assertTrue(result["actionable"])
        self.assertEqual(result["identities"]["student"], "Sipei Yao")
        self.assertEqual(result["identities"]["addressee"]["name"], "Roberts")
        self.assertEqual(result["identities"]["addressee"]["email"],
                         "martin.roberts@example.edu")
        self.assertTrue(any("salutation" in reason for reason in result["reasons"]))

    def test_person_named_file_is_classified_from_letter_schema_not_filename(self):
        # The file name is only a person name; there is no Email: declaration.
        result = recognize_bytes("Ping Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE))
        self.assertEqual(result["type"], OUTREACH_DRAFT)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["identities"]["student"], "Shen Hui")
        self.assertEqual(result["identities"]["addressee"]["name"], "Tan")
        self.assertEqual(result["identities"]["addressee"]["email"], "")
        self.assertTrue(any("No recipient address" in caution
                            for caution in result["cautions"]))

    def test_outreach_topic_words_without_letter_envelope_are_not_a_draft(self):
        prose = [
            "套磁工作记录：今天整理了导师邮箱和学校清单。",
            "需要核对奖学金路径与个人主页链接，发送前再确认研究方向。",
            "导师姓名与职称分列，后续补充邮件状态。",
        ]
        result = recognize_bytes("notes.docx", docx_bytes(prose))
        self.assertNotIn(result["type"], (OUTREACH_DRAFT, MULTI_DRAFT_BUNDLE))
        self.assertFalse(result["actionable"])

    def test_salutation_without_signoff_stays_below_high_confidence(self):
        paragraphs = DRAFT_WITHOUT_ENVELOPE[:-2]  # drop sign-off and sender name
        result = recognize_bytes("fragment.docx", docx_bytes(paragraphs))
        self.assertIn(result["type"], (OUTREACH_DRAFT, UNKNOWN, AMBIGUOUS))
        if result["type"] == OUTREACH_DRAFT:
            self.assertNotEqual(result["confidence"], "high")


class MultiDraftBundleTests(unittest.TestCase):
    def setUp(self):
        self.paragraphs = [
            "Junhao Jiao",
            "2.",
            "Daniel Lock — Loughborough University London",
            "Subject: PhD Application Fall 2027 — Junhao Jiao｜Sports",
            "Dear Prof. Lock,",
            "I hope this email finds you well. My name is Junhao Jiao and I am "
            "writing to express my interest in your research group.",
            "Your work on fan engagement aligns with my aspirations. My CV is attached.",
            "Yours sincerely,",
            "Junhao Jiao",
            "✏️ 契合点：社会认同",
            "📧 monica.chien@example.edu",
            "3.",
            "Monica Chien — University of Queensland",
            "Subject: PhD Application Fall 2027 — Consumer Behaviour",
            "Dear Prof. Chien,",
            "I hope this email finds you well. My name is Junhao Jiao and I am "
            "writing to express interest. Your research on sponsorship is inspiring. "
            "My CV is attached.",
            "Yours sincerely,",
            "Junhao Jiao",
            "### 3. Neil Li (李恒运) — neil.li@example.edu",
            "Dear Prof. Li,",
            "I hope this email finds you well. My name is Junhao Jiao and I am "
            "writing about PhD supervision. Your paper deeply resonates with me. "
            "My CV is attached.",
            "Yours sincerely,",
            "Junhao Jiao",
        ]

    def test_repeated_envelope_segments_into_separate_supervisors(self):
        result = recognize_bytes("letters.docx", docx_bytes(self.paragraphs))
        self.assertEqual(result["type"], MULTI_DRAFT_BUNDLE)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["identities"]["student"], "Junhao Jiao")
        segments = result["segments"]
        self.assertEqual([s["supervisor"] for s in segments],
                         ["Daniel Lock", "Monica Chien", "Neil Li (李恒运)"])
        # The dangling email marker belongs to the section heading that follows it.
        self.assertEqual(segments[0]["emails"], [])
        self.assertEqual(segments[1]["emails"], ["monica.chien@example.edu"])
        # The markdown 'Name — email' heading carries the address directly.
        self.assertEqual(segments[2]["emails"], ["neil.li@example.edu"])
        self.assertTrue(any("no recipient" in caution for caution in result["cautions"]))

    def test_single_letter_is_not_segmented_as_a_bundle(self):
        result = recognize_bytes("one.docx", docx_bytes(DRAFT_WITH_ENVELOPE))
        self.assertEqual(result["type"], OUTREACH_DRAFT)
        self.assertEqual(result["segments"], [])


class CurriculumVitaeTests(unittest.TestCase):
    def test_applicant_cv_is_bindable_candidate_with_student_identity(self):
        result = recognize_bytes("Zige_Wu_CV.docx", docx_bytes(APPLICANT_CV_PARAGRAPHS))
        self.assertEqual(result["type"], APPLICANT_CV)
        self.assertEqual(result["confidence"], "high")
        self.assertTrue(result["actionable"])
        self.assertEqual(result["identities"]["student"], "Test Student")
        self.assertEqual(result["identities"]["cv_role"], "applicant")
        self.assertEqual(result["identities"]["contact_email"], "student@example.com")

    def test_faculty_cv_is_reference_and_never_a_student_attachment(self):
        result = recognize_bytes("Qian-CV.docx", docx_bytes(SCHOLAR_CV_PARAGRAPHS))
        self.assertEqual(result["type"], SCHOLAR_CV)
        self.assertFalse(result["actionable"])
        self.assertEqual(result["identities"]["cv_role"], "scholar")
        self.assertEqual(result["identities"]["student"], "")
        self.assertTrue(any("must not auto-bind" in reason for reason in result["reasons"]))

    def test_letter_envelope_absent_is_a_required_gate(self):
        # Even a faculty-looking letter is a letter, not a CV, when addressed.
        result = recognize_bytes("Prof Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE))
        self.assertEqual(result["type"], OUTREACH_DRAFT)


class NonLetterDocumentTests(unittest.TestCase):
    def test_maintenance_log_is_catalogue_not_letters(self):
        paragraphs = [
            "📌 总览", "学生", "邮件数", "定位",
            "李锦航", "10", "打开学生页",
            "👤 李锦航｜第一轮（5）", "导师", "学校", "邮件", "作品链接",
            "Hao Chen", "香港科技大学", "打开邮件",
            "Medical AI paper", "https://arxiv.org/abs/2404.15127",
            "Lequan Yu", "香港大学", "打开邮件",
            "Missing-modality learning", "https://doi.org/10.1000/abc",
            "Qi Dou", "香港中文大学", "打开邮件",
            "Federated learning study", "https://doi.org/10.1000/def",
        ]
        result = recognize_bytes("youyue 邮件维护日志.docx", docx_bytes(paragraphs))
        self.assertEqual(result["type"], MAINTENANCE_LOG)
        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["actionable"])

    def test_period_headed_timeline_is_planning_document(self):
        paragraphs = [
            "某同学 2028-2029 硕士申请时间规划",
            "简要时间轴",
            "2026 年 8 月-2027 年 2 月",
            "• 探索方向并形成院校长名单",
            "• 梳理先修课差距与科研经历",
            "2027 年 3 月-6 月",
            "• 完成学术 CV 初稿与推荐人沟通",
            "• 安排语言考试节点",
            "2027 年 7 月-9 月",
            "• 建立导师池并准备 EOI 材料",
            "• 首轮联系高匹配导师",
        ]
        result = recognize_bytes("plan.docx", docx_bytes(paragraphs))
        self.assertEqual(result["type"], PLANNING_DOCUMENT)
        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["actionable"])


class WorkbookRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_supervisor_roster_with_person_rows_and_addresses(self):
        path = workbook_file(self.directory, "master.xlsx", [(
            "Sheet1", [
                ["城市", "大学", "导师", "邮箱📮", "URL"],
                ["Melbourne", "Example University", "Dr Alex Green", "alex@example.edu",
                 "https://example.edu/alex"],
                ["Sydney", "Other University", "Dr Blair Blue", "blair@example.edu",
                 "https://example.edu/blair"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)
        self.assertEqual(result["confidence"], "high")
        self.assertTrue(result["actionable"])
        self.assertEqual(result["identities"]["email_count"], 2)

    def test_workflow_template_is_tracking_sheet_not_master(self):
        path = workbook_file(self.directory, "tracker.xlsx", [
            ("工作表1", [
                ["学校", "专业", "套磁", "导师筛选", "邮箱", "个人主页"],
                ["【AI填写】学校官方英文名称", "【AI填写】专业名称",
                 "【AI判定】outreach priority", "【AI填写】导师姓名",
                 "【AI填写】公开邮箱；无法核实时写 Need Verification",
                 "【AI填写】个人主页 URL"],
            ]),
            ("AI使用指令", [
                ["AI-Assisted PhD Supervisor Outreach Tracker"],
                ["Copy-ready Professional Instruction"],
            ]),
        ])
        result = recognize_file(path)
        self.assertEqual(result["type"], TRACKING_SHEET)
        self.assertFalse(result["actionable"])
        self.assertTrue(any("template" in reason for reason in result["reasons"]))

    def test_program_catalogue_with_banner_and_zero_emails_is_reference(self):
        path = workbook_file(self.directory, "programs.xlsx", [(
            "教育心理", [
                ["2027 心理学硕士项目总表"],
                [],
                ["ID", "学校", "项目名称", "学位类型", "学制", "英语要求", "项目主页"],
                [1, "UCL", "MSc Psychology of Education", "MSc", "1年", "IELTS 7.5",
                 "https://www.ucl.ac.uk/program"],
                [2, "KCL", "MSc Developmental Psychology", "MSc", "1年", "Band 7",
                 "https://www.kcl.ac.uk/program"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], PROGRAM_REFERENCE)
        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["actionable"])

    def test_bilingual_statute_dataset_is_unrelated(self):
        rows = [["Chinese_Source", "English_Translation_Marked", "Collocation"]]
        for index in range(12):
            rows.append([
                f"第一千二百{index}条　建筑物倒塌造成他人损害的，由建设单位承担责任。",
                f"Article 12{index} Where a building collapses and causes damage, "
                "the construction unit shall bear liability.",
                "any",
            ])
        path = workbook_file(self.directory, "未命名电子表格.xlsx",
                             [("any_extracted_results", rows)])
        result = recognize_file(path)
        self.assertEqual(result["type"], UNRELATED)
        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["actionable"])

    def test_empty_workbook_stays_unknown(self):
        path = workbook_file(self.directory, "blank.xlsx", [("Sheet1", [])])
        result = recognize_file(path)
        self.assertEqual(result["type"], UNKNOWN)
        self.assertFalse(result["actionable"])

    def test_program_fields_do_not_hijack_a_real_master_sheet(self):
        path = workbook_file(self.directory, "master.xlsx", [(
            "Sheet1", [
                ["大学", "导师", "邮箱", "备注"],
                ["Example University", "Dr Alex Green", "alex@example.edu", "优先"],
                ["Other University", "Dr Blair Blue", "blair@example.edu", "待定"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)

    def test_merged_institution_reaches_every_supervisor_row(self):
        # One university cell merged across its three supervisors: the value
        # lives in the top-left cell only, so the reader sees two blanks.
        path = merged_workbook_file(
            self.directory, "merged.xlsx", "名单",
            [["大学", "导师", "邮箱"],
             ["A 大学", "张三", "a@example.edu"],
             ["B 大学", "李四", "b@example.edu"],
             [None, "王五", "c@example.edu"],
             [None, "赵六", "d@example.edu"]],
            [("A3", "A5")])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)
        self.assertEqual(result["identities"]["row_count"], 4)
        self.assertEqual(result["identities"]["email_count"], 4)

    def test_decorated_and_english_headers_are_recognized(self):
        path = workbook_file(self.directory, "roster.xlsx", [(
            "Sheet1", [
                ["Professor", "Affiliation", "E-mail Address", "Homepage"],
                ["Alex Green", "Example University", "alex@example.edu",
                 "https://example.edu/alex"],
                ["Blair Blue", "Other University", "blair@example.edu",
                 "https://example.edu/blair"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)
        self.assertEqual(result["confidence"], "high")

    def test_header_row_below_a_banner_and_preamble_is_found(self):
        path = workbook_file(self.directory, "deep.xlsx", [(
            "Sheet1", [
                ["2027 导师联系总表"],
                [],
                [],
                ["备注：仅第一轮联系"],
                ["大学", "导师", "邮箱", "研究方向"],
                ["Example University", "Dr Alex Green", "alex@example.edu",
                 "computational linguistics"],
                ["Other University", "Dr Blair Blue", "blair@example.edu",
                 "psycholinguistics"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)
        self.assertEqual(result["evidence"]["sheets"][0]["header_row"], 5)
        self.assertEqual(result["identities"]["row_count"], 2)

    def test_institution_and_address_roster_without_names_is_reported(self):
        path = workbook_file(self.directory, "contacts.xlsx", [(
            "Sheet1", [
                ["院校", "联系邮箱", "主页"],
                ["Example University", "grad@example.edu", "https://example.edu/grad"],
                ["Other University", "admissions@example.edu", "https://example.edu/ad"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], SUPERVISOR_MASTER)
        self.assertTrue(any("no supervisor column" in reason
                            for reason in result["reasons"]))
        self.assertTrue(any("No supervisor/name column" in caution
                            for caution in result["cautions"]))

    def test_address_column_without_addresses_is_cautioned(self):
        path = workbook_file(self.directory, "unfilled.xlsx", [(
            "Sheet1", [
                ["大学", "导师", "邮箱"],
                ["Example University", "Dr Alex Green", "【AI填写】公开邮箱"],
                ["Other University", "Dr Blair Blue", "Need Verification"],
            ])])
        result = recognize_file(path)
        self.assertTrue(any("well-formed addresses" in caution
                            for caution in result["cautions"]))

    def test_unlabelled_address_column_is_reported_not_guessed(self):
        path = workbook_file(self.directory, "odd.xlsx", [(
            "Sheet1", [
                ["序号", "姓名", "备注"],
                ["1", "Alex Green", "alex@example.edu"],
                ["2", "Blair Blue", "blair@example.edu"],
            ])])
        result = recognize_file(path)
        self.assertEqual(result["type"], UNKNOWN)
        columns = result["evidence"]["sheets"][0]["unlabelled_columns"]
        self.assertTrue(any(item["field"] == "address" for item in columns))
        self.assertTrue(any("no header" in caution for caution in result["cautions"]))


class BulkImportCsvTests(unittest.TestCase):
    def test_outgoing_envelope_rows_are_batch_import(self):
        rows = [
            ["编号", "收件人", "主题", "正文", "附件", "定时时间"],
            ["001", "a@example.edu", "Subject A",
             "Dear Prof. A,\n\nI hope this email finds you well. Long letter body "
             "with purpose and attachment mention.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-27 07:30"],
            ["002", "", "Subject B",
             "Dear Prof. B,\n\nAnother complete personalized letter body of meaningful "
             "length for the second supervisor here.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-28 07:30"],
            ["003", "c@example.edu", "Subject C",
             "Dear Prof. C,\n\nThe third complete personalized letter body also carries "
             "enough discourse to be a full message.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-29 07:30"],
        ]
        result = recognize_bytes("import.csv", csv_bytes(rows))
        self.assertEqual(result["type"], BULK_IMPORT)
        self.assertEqual(result["confidence"], "high")
        self.assertTrue(result["actionable"])
        self.assertEqual(result["identities"]["row_count"], 3)
        self.assertEqual(result["identities"]["recipient_count"], 2)
        self.assertEqual(result["identities"]["attachments"], ["Student-CV.pdf"])
        self.assertTrue(any("rows lack a recipient" in caution
                            for caution in result["cautions"]))

    def test_non_envelope_csv_is_not_forced_into_batch_import(self):
        rows = [
            ["日期", "文件夹", "状态"],
            ["2026-09-01", "Sent", "已发送"],
            ["2026-09-02", "Inbox", "已回复"],
        ]
        result = recognize_bytes("records.csv", csv_bytes(rows))
        self.assertNotEqual(result["type"], BULK_IMPORT)


class DelimitedTextTests(unittest.TestCase):
    """Extensions and separators a .csv-only reader could not handle."""

    def _batch_rows(self):
        return [
            ["编号", "收件人", "主题", "正文", "附件", "定时时间"],
            ["001", "a@example.edu", "Subject A",
             "Dear Prof. A,\n\nI hope this email finds you well. Long letter body "
             "with purpose and attachment mention.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-27 07:30"],
            ["002", "b@example.edu", "Subject B",
             "Dear Prof. B,\n\nAnother complete personalized letter body of meaningful "
             "length for the second supervisor here.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-28 07:30"],
            ["003", "c@example.edu", "Subject C",
             "Dear Prof. C,\n\nThe third complete personalized letter body also carries "
             "enough discourse to be a full message.\n\nYours sincerely,\nStudent",
             "Student-CV.pdf", "2026-08-29 07:30"],
        ]

    def test_semicolon_separated_batch_is_recognized(self):
        result = recognize_bytes("batch.csv",
                                 csv_bytes(self._batch_rows(), delimiter=";"))
        self.assertEqual(result["type"], BULK_IMPORT)
        self.assertEqual(result["identities"]["row_count"], 3)
        self.assertEqual(result["identities"]["recipient_count"], 3)
        self.assertEqual(result["evidence"]["delimiter"], ";")

    def test_tab_separated_batch_is_recognized(self):
        result = recognize_bytes("batch.tsv",
                                 csv_bytes(self._batch_rows(), delimiter="\t"))
        self.assertEqual(result["type"], BULK_IMPORT)
        self.assertEqual(result["identities"]["row_count"], 3)

    def test_plain_text_that_is_not_a_table_stays_unknown(self):
        result = recognize_bytes("notes.txt", "第一封邮件\n第二封邮件\n".encode("utf-8"))
        self.assertEqual(result["type"], UNKNOWN)
        self.assertFalse(result["actionable"])
        self.assertTrue(any("single-column" in caution for caution in result["cautions"]))

    def test_gb18030_encoded_batch_is_decoded(self):
        result = recognize_bytes("batch.csv",
                                 csv_bytes(self._batch_rows()).decode("utf-8")
                                 .encode("gb18030"))
        self.assertEqual(result["type"], BULK_IMPORT)

    def test_delimiter_is_chosen_from_column_shape_not_character_counts(self):
        # Every body carries commas; the file is semicolon-separated.
        text = csv_bytes(self._batch_rows(), delimiter=";").decode("utf-8-sig")
        self.assertEqual(detect_delimiter(text), ";")
        self.assertEqual(detect_delimiter("a\tb\tc\nd\te\tf"), "\t")
        self.assertEqual(detect_delimiter("编号,收件人,主题\n1,a@x.edu,s"), ",")


class ColumnProfileTests(unittest.TestCase):
    def test_profile_measures_the_value_shape_of_a_column(self):
        profile = profile_column(0, "邮箱", ["a@example.edu", "b@example.edu", "待补充"])
        self.assertEqual(profile.filled, 3)
        self.assertAlmostEqual(profile.email_ratio, 2 / 3)
        self.assertEqual(profile.unique_ratio, 1.0)

    def test_empty_column_profile_is_safe(self):
        profile = profile_column(0, "", [])
        self.assertEqual(profile.filled, 0)
        self.assertEqual(data_field_hints(profile), [])

    def test_hints_name_the_field_the_values_support(self):
        addresses = profile_column(0, "", ["a@example.edu", "b@example.edu"])
        self.assertEqual(data_field_hints(addresses)[0][0], "address")
        names = profile_column(1, "", ["Student-CV.pdf", "Transcript.pdf"])
        self.assertEqual(data_field_hints(names)[0][0], "attachment")
        dates = profile_column(2, "", ["2026-08-27", "2026-08-28"])
        self.assertEqual(data_field_hints(dates)[0][0], "schedule")

    def test_normalization_keeps_compound_labels_distinct(self):
        self.assertEqual(normalize_header("邮箱 📮"), normalize_header("邮箱"))
        self.assertEqual(normalize_header("E-mail Address"), normalize_header("emailaddress"))
        self.assertNotEqual(normalize_header("导师筛选"), normalize_header("导师"))
        self.assertNotEqual(normalize_header("所属院校"), normalize_header("院校"))


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_exact_bytes_are_exact_duplicates(self):
        data = docx_bytes(DRAFT_WITH_ENVELOPE)
        collection = recognize_collection([("a.docx", data), ("b.docx", bytes(data))])
        relations = collection["relations"]
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["relation"], "exact_duplicate")

    def test_rewritten_timeline_with_version_marker_is_near_duplicate(self):
        original = [
            "某同学 2028-2029 硕士申请时间规划",
            "2026 年 8 月-2027 年 2 月",
            "• 探索研究方向，比较心理学与认知科学方向的可行性和课程要求",
            "• 形成四地区院校长名单并标注奖学金路径、学制与申请轮次",
            "• 梳理先修课差距、科研经历与统计编程训练的补强方案",
            "2027 年 3 月-6 月",
            "• 完成学术 CV 初稿、推荐素材包与语言考试时间安排",
            "• 开展系统文献综述和研究方法训练，形成研究报告初稿",
            "2027 年 7 月-9 月",
            "• 建立澳洲导师池，逐校记录研究匹配、招生容量与联系状态",
            "• 准备 EOI 材料并分批联系高匹配导师，确认申请流程",
        ]
        backup = [
            "某同学 2028-2029 硕士申请时间规划",
            "2026 年 8 月-2027 年 2 月",
            "• 确定双轨方向、项目边界与院校池，完成顶层设计",
            "• 初步确认香港与英国院校名单，建立导师池与难度分级",
            "2027 年 3 月-6 月",
            "• 补强科研方法，整理 CV、推荐人、语言与材料框架",
            "• 学术 CV 打磨，研究经历按问题方法数据结果学术化总结",
            "2027 年 7 月-9 月",
            "• 建立澳洲导师池 / EOI，筛选研究型项目并核对招生机制",
            "• 准备研究型材料包：CV、成绩单、研究计划与套磁信初稿",
        ]
        a = docx_file(self.temp.name, "某同学2028-2029硕士申请时间规划.docx", original).read_bytes()
        b = docx_file(self.temp.name, "某同学2028-2029硕士申请时间规划（原版备份）.docx", backup).read_bytes()
        relations = detect_relations(
            [("某同学2028-2029硕士申请时间规划.docx", a),
             ("某同学2028-2029硕士申请时间规划（原版备份）.docx", b)])
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["relation"], "near_duplicate")
        self.assertTrue(any("version markers" in basis for basis in relations[0]["basis"]))

    def test_unrelated_titles_do_not_pair(self):
        a = docx_file(self.temp.name, "某同学2028-2029硕士申请时间规划.docx",
                      ["某同学 2028-2029 硕士申请时间规划",
                       "2026 年 8 月-2027 年 2 月", "• 任务A", "• 任务B"]).read_bytes()
        b = docx_file(self.temp.name, "邮件维护日志.docx",
                      ["📌 总览", "打开邮件", "https://doi.org/10.1/x"]).read_bytes()
        relations = detect_relations(
            [("某同学2028-2029硕士申请时间规划.docx", a), ("邮件维护日志.docx", b)])
        self.assertEqual(relations, [])


class RecognitionBridgeTests(unittest.TestCase):
    """The stdio UI bridge: pre-import recognition and persisted revisions."""

    def setUp(self):
        import base64 as b64
        from smartmail import SmartMail
        from smartmail.ui import dispatch as ui_dispatch

        self.dispatch = ui_dispatch
        self.b64encode = b64.b64encode
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "store"
        self.core = SmartMail(self.home)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("Recognition bridge")
        self.student = self.core.create_student("Test Student", "student@163.com")
        master_path = Path(self.temp.name) / "master.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append(["大学", "导师", "邮箱📮", "URL"])
        sheet.append(["Example University", "Dr Alex Green", "alex@example.edu",
                      "https://example.edu/alex"])
        workbook.save(master_path)
        workbook.close()
        self.master_bytes = master_path.read_bytes()
        self.cv_bytes = docx_bytes(APPLICANT_CV_PARAGRAPHS)
        self.plan_bytes = docx_bytes([
            "某同学 2028-2029 硕士申请时间规划",
            "2026 年 8 月-2027 年 2 月",
            "• 探索研究方向并形成院校长名单",
            "• 梳理先修课差距与科研经历",
            "2027 年 3 月-6 月",
            "• 完成学术 CV 初稿与推荐人沟通",
            "• 安排语言考试节点",
            "2027 年 7 月-9 月",
            "• 建立导师池并准备 EOI 材料",
        ])

    def _upload(self, name, data, revised_type=None):
        item = {"name": name, "content": self.b64encode(data).decode("ascii")}
        if revised_type:
            item["type"] = revised_type
        return item

    def test_recognize_command_classifies_without_persisting_anything(self):
        result = self.dispatch(self.core, {"command": "intake_recognize", "files": [
            self._upload("Ping Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE)),
            self._upload("plan.docx", self.plan_bytes),
        ]})
        by_name = {source["name"]: source for source in result["sources"]}
        self.assertEqual(by_name["Ping Tan.docx"]["type"], OUTREACH_DRAFT)
        self.assertEqual(by_name["plan.docx"]["type"], PLANNING_DOCUMENT)
        # Recognition is advisory: reviewing files creates no import or tasks.
        self.assertEqual(self.core.list_imports(self.campaign["id"]), [])
        self.assertEqual(self.core.list_tasks(self.campaign["id"]), [])

    def test_import_persists_types_and_uses_them_for_stable_categories(self):
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [
                                               self._upload("master.xlsx", self.master_bytes),
                                               self._upload("Test Student_CV.docx", self.cv_bytes),
                                               self._upload("plan.docx", self.plan_bytes),
                                           ]})
        workspace = result["workspace"]
        recognition = workspace["source_recognition"]
        categories = workspace["source_categories"]
        by_name = {source["name"]: (source["id"], recognition.get(source["id"]),
                                    categories[source["id"]])
                   for imported in workspace["imports"] for source in imported["sources"]}
        master_id, master_note, master_category = by_name["master.xlsx"]
        self.assertEqual(master_category, "master")
        self.assertEqual(master_note["type"], SUPERVISOR_MASTER)
        self.assertFalse(master_note["revised"])
        cv_id, cv_note, cv_category = by_name["Test Student_CV.docx"]
        self.assertEqual(cv_category, "attachments")
        self.assertEqual(cv_note["type"], APPLICANT_CV)
        self.assertEqual(cv_note["identities"]["cv_role"], "applicant")
        _plan_id, plan_note, plan_category = by_name["plan.docx"]
        self.assertEqual(plan_category, "unresolved")
        self.assertEqual(plan_note["type"], PLANNING_DOCUMENT)
        self.assertFalse(plan_note["actionable"])

    def test_operator_revision_overrides_effective_type_and_category(self):
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [
                                               self._upload("master.xlsx", self.master_bytes),
                                               self._upload("Test Student_CV.docx",
                                                            self.cv_bytes,
                                                            revised_type=SCHOLAR_CV),
                                           ]})
        recognition = result["workspace"]["source_recognition"]
        note = next(note for note in recognition.values()
                    if note.get("identities", {}).get("person") == "Test Student")
        self.assertEqual(note["recognized_type"], APPLICANT_CV)
        self.assertEqual(note["type"], SCHOLAR_CV)
        self.assertTrue(note["revised"])
        self.assertFalse(note["actionable"])
        categories = result["workspace"]["source_categories"]
        cv_id = next(source["id"] for imported in result["workspace"]["imports"]
                     for source in imported["sources"] if source["name"] == "Test Student_CV.docx")
        self.assertEqual(categories[cv_id], "unresolved")


class MasterlessImportBridgeTests(unittest.TestCase):
    """ZIP expansion and draft-created Tasks without a supervisor master list."""

    def setUp(self):
        import base64 as b64
        from smartmail import SmartMail
        from smartmail.ui import dispatch as ui_dispatch

        self.dispatch = ui_dispatch
        self.b64encode = b64.b64encode
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.core = SmartMail(Path(self.temp.name) / "store")
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("Masterless")
        self.student = self.core.create_student("Shen Hui", "shenhui@163.com")

    def _archive(self, name, members):
        path = Path(self.temp.name) / name
        with zipfile.ZipFile(path, "w") as archive:
            for member_name, data in members:
                archive.writestr(member_name, data)
        return path.read_bytes()

    def _upload(self, name, data, included=True, members=None):
        item = {"name": name, "content": self.b64encode(data).decode("ascii"),
                "included": included}
        if members is not None:
            item["members"] = members
        return item

    def test_recognize_flattens_zip_members_instead_of_returning_a_mixed_row(self):
        archive = self._archive("pack.zip", [
            ("Ping Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE)),
            ("master.xlsx", self._master_bytes()),
        ])
        result = self.dispatch(self.core, {"command": "intake_recognize", "files": [
            self._upload("pack.zip", archive)]})
        names = sorted(source["name"] for source in result["sources"])
        self.assertNotIn("pack.zip", names)
        self.assertEqual(names, ["Ping Tan.docx", "master.xlsx"])
        self.assertTrue(all(source.get("container") == "pack.zip"
                            for source in result["sources"]))
        by_name = {s["name"]: s["type"] for s in result["sources"]}
        self.assertEqual(by_name["Ping Tan.docx"], OUTREACH_DRAFT)
        self.assertEqual(by_name["master.xlsx"], SUPERVISOR_MASTER)

    def _master_bytes(self):
        return workbook_file(Path(self.temp.name), "m.xlsx", [("Sheet1", [
            ["大学", "导师", "邮箱📮", "URL"],
            ["Example University", "Dr Alex Green", "alex@example.edu", ""],
        ])]).read_bytes()

    def test_draft_only_zip_creates_task_and_preparation_without_master(self):
        archive = self._archive("letters.zip", [
            ("Ping Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE))])
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [self._upload("letters.zip", archive)]})
        self.assertEqual(result["import"]["summary"]["rows"], 0)
        self.assertEqual(len(result["preparation"]["preparation_ids"]), 1)
        tasks = result["workspace"]["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task"]["supervisor"]["name"], "Tan")
        self.assertEqual(tasks[0]["task"]["supervisor"]["addresses"], [])
        self.assertTrue(any(exception["code"] == "invalid_recipient"
                            for exception in tasks[0]["task"]["exceptions"]))

    def test_member_filter_expands_only_approved_members(self):
        archive = self._archive("pack.zip", [
            ("Ping Tan.docx", docx_bytes(DRAFT_WITHOUT_ENVELOPE)),
            ("申请时间规划.docx", docx_bytes([
                "某同学 2028-2029 硕士申请时间规划",
                "2026 年 8 月-2027 年 2 月", "• 探索方向并形成院校长名单",
                "2027 年 3 月-6 月", "• 完成学术 CV 初稿",
                "2027 年 7 月-9 月", "• 建立导师池",
            ])),
        ])
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [self._upload("pack.zip", archive, members=[
                                               {"name": "Ping Tan.docx"},
                                           ])]})
        names = [source["name"] for imported in result["workspace"]["imports"]
                 for source in imported["sources"]]
        self.assertEqual(names, ["Ping Tan.docx"])
        self.assertEqual(len(result["workspace"]["tasks"]), 1)

    def test_multi_draft_bundle_creates_one_task_per_segment(self):
        paragraphs = [
            "2.", "Daniel Lock — Loughborough University London",
            "Subject: PhD Application Fall 2027 — Junhao Jiao｜Sports",
            "Dear Prof. Lock,",
            "I hope this email finds you well. My name is Junhao Jiao and I am writing "
            "to express interest. Your work inspires me. My CV is attached.",
            "Yours sincerely,", "Junhao Jiao",
            "📧 monica.chien@example.edu",
            "3.", "Monica Chien — University of Queensland",
            "Subject: PhD Application — Consumer Behaviour",
            "Dear Prof. Chien,",
            "I hope this email finds you well. My name is Junhao Jiao and I am writing "
            "to inquire. Your research resonates. My CV is attached.",
            "Yours sincerely,", "Junhao Jiao",
        ]
        archive = self._archive("bundle.zip", [("letters.docx", docx_bytes(paragraphs))])
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [self._upload("bundle.zip", archive)]})
        self.assertEqual(len(result["preparation"]["preparation_ids"]), 2)
        tasks = {t["task"]["supervisor"]["name"]: t for t in result["workspace"]["tasks"]}
        self.assertEqual(set(tasks), {"Daniel Lock", "Monica Chien"})
        self.assertEqual(tasks["Monica Chien"]["task"]["supervisor"]["addresses"],
                         ["monica.chien@example.edu"])
        preparation = next(
            p for p in (self.core.get_preparation(pid)
                        for pid in result["preparation"]["preparation_ids"])
            if p["association"]["supervisor"] == "Monica Chien")
        self.assertIn("PhD Application", preparation["subject"])
        self.assertTrue(preparation["ready"])

    def test_reference_only_set_is_preserved_without_creating_work(self):
        archive = self._archive("refs.zip", [("申请时间规划.docx", docx_bytes([
            "某同学 2028-2029 硕士申请时间规划",
            "2026 年 8 月-2027 年 2 月", "• 探索方向并形成院校长名单",
            "2027 年 3 月-6 月", "• 完成学术 CV 初稿",
            "2027 年 7 月-9 月", "• 建立导师池",
        ]))])
        result = self.dispatch(self.core, {"command": "intake_import",
                                           "campaign_id": self.campaign["id"],
                                           "student_id": self.student["id"],
                                           "files": [self._upload("refs.zip", archive)]})
        self.assertEqual(result["preparation"]["preparation_ids"], [])
        self.assertEqual(result["workspace"]["tasks"], [])
        self.assertEqual(len(result["workspace"]["imports"][0]["sources"]), 1)


@unittest.skipUnless(
    os.environ.get("SMARTMAIL_RECOGNITION_FULLSET"),
    "Set SMARTMAIL_RECOGNITION_FULLSET to the extracted fullset directory")
class FullsetCorpusTests(unittest.TestCase):
    """The curated 14-source corpus: classic set plus adversarial hard cases."""

    EXPECTED = (
        ("Martin Roberts.docx", OUTREACH_DRAFT),
        ("Kanglong Liu.docx", OUTREACH_DRAFT),
        ("Ping Tan.docx", OUTREACH_DRAFT),
        ("Yixuan Yuan.docx", OUTREACH_DRAFT),
        ("Zige_Wu_CV.docx", APPLICANT_CV),
        ("Qian-CV.docx", SCHOLAR_CV),
        ("sample2.docx", MULTI_DRAFT_BUNDLE),
        ("youyue", MAINTENANCE_LOG),
        ("时间规划.docx", PLANNING_DOCUMENT),
        ("时间规划（原版备份）.docx", PLANNING_DOCUMENT),
        ("姚思培", SUPERVISOR_MASTER),
        ("套磁跟进", TRACKING_SHEET),
        ("新加坡教育心理学", PROGRAM_REFERENCE),
        ("未命名电子表格", UNRELATED),
        ("全量56人", BULK_IMPORT),
    )

    def setUp(self):
        self.root = Path(os.environ["SMARTMAIL_RECOGNITION_FULLSET"])

    def _sources(self):
        members = []
        for path in self.root.rglob("*"):
            if path.suffix.lower() in (".docx", ".xlsx", ".csv"):
                members.append((path.name, path.read_bytes()))
        return members

    def test_every_source_is_classified_high_confidence_as_expected(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        self.assertEqual(len(results), len(self.EXPECTED))
        for token, expected_type in self.EXPECTED:
            with self.subTest(token=token):
                matches = [name for name in results if token in name]
                self.assertEqual(len(matches), 1, f"expected exactly one file containing {token}")
                result = results[matches[0]]
                self.assertEqual(result["type"], expected_type,
                                 f"{matches[0]} -> {result['type']}: {result['cautions']}")
                self.assertEqual(result["confidence"], "high")
                self.assertTrue(result["reasons"], "classification must carry reasons")

    def test_name_only_drafts_derive_identity_from_discourse(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        ping = next(result for name, result in results.items() if name == "Ping Tan.docx")
        self.assertEqual(ping["identities"]["student"], "Shen Hui")
        self.assertEqual(ping["identities"]["addressee"]["name"], "Tan")
        self.assertEqual(ping["identities"]["addressee"]["email"], "")
        yuan = next(result for name, result in results.items() if name == "Yixuan Yuan.docx")
        self.assertEqual(yuan["identities"]["student"], "Shen Hui")

    def test_cv_role_separation(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        applicant = next(result for name, result in results.items()
                         if name == "Zige_Wu_CV.docx")
        scholar = next(result for name, result in results.items()
                       if name == "Qian-CV.docx")
        self.assertEqual(applicant["identities"]["cv_role"], "applicant")
        self.assertTrue(applicant["actionable"])
        self.assertEqual(scholar["identities"]["cv_role"], "scholar")
        self.assertFalse(scholar["actionable"])

    def test_bundle_segments_separately_and_flags_missing_addresses(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        bundle = next(result for name, result in results.items()
                      if name == "sample2.docx")
        self.assertGreaterEqual(len(bundle["segments"]), 50)
        addressed = [segment for segment in bundle["segments"] if segment["emails"]]
        self.assertGreaterEqual(len(addressed), 40)
        self.assertEqual(bundle["identities"]["student"], "Junhao Jiao")
        self.assertTrue(any(segment["supervisor"] == "Daniel Lock"
                            and not segment["emails"]
                            for segment in bundle["segments"]))

    def test_master_program_tracking_and_unrelated_sheets_are_distinct(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        master = next(result for name, result in results.items() if "姚思培" in name)
        self.assertGreaterEqual(master["identities"]["email_count"], 50)
        program = next(result for name, result in results.items()
                       if "新加坡教育心理学" in name)
        self.assertFalse(program["actionable"])
        tracking = next(result for name, result in results.items() if "套磁跟进" in name)
        self.assertEqual(tracking["type"], TRACKING_SHEET)
        unrelated = next(result for name, result in results.items()
                         if "未命名电子表格" in name)
        self.assertEqual(unrelated["type"], UNRELATED)

    def test_bulk_csv_preserves_rows_and_missing_recipient_caution(self):
        results = {name: recognize_bytes(name, data)
                   for name, data in self._sources()}
        bulk = next(result for name, result in results.items() if "全量56人" in name)
        self.assertEqual(bulk["identities"]["row_count"], 56)
        self.assertGreaterEqual(bulk["identities"]["recipient_count"], 50)
        self.assertTrue(any("rows lack a recipient" in caution
                            for caution in bulk["cautions"]))

    def test_planning_pair_is_reported_as_near_duplicate_without_collapse(self):
        members = self._sources()
        collection = recognize_collection(members)
        planning = [relation for relation in collection["relations"]
                    if "时间规划" in relation["a"] and "时间规划" in relation["b"]]
        self.assertEqual(len(planning), 1)
        self.assertEqual(planning[0]["relation"], "near_duplicate")
        self.assertTrue(any("原版备份" in basis for basis in planning[0]["basis"]))


if __name__ == "__main__":
    unittest.main()
