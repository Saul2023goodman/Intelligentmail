"""Generate small recognition verification fixtures for the browser flow."""
import os
import zipfile
from io import BytesIO

from openpyxl import Workbook

BASE = os.path.join(os.path.dirname(__file__), "verify")
os.makedirs(BASE, exist_ok=True)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(path, paragraphs):
    from xml.sax.saxutils import escape
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:p>' for t in paragraphs)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


# 1. one-row supervisor master
wb = Workbook()
ws = wb.active
ws.title = "Sheet1"
ws.append(["大学", "导师", "邮箱📮", "URL"])
ws.append(["Example University", "Dr Alex Green", "alex@example.edu",
           "https://example.edu/alex"])
wb.save(os.path.join(BASE, "导师名单.xlsx"))
wb.close()

# 2. person-name-only draft without an Email declaration
docx(os.path.join(BASE, "Alex Green.docx"), [
    "Dear Dr Green,",
    "I hope this email finds you well.",
    "I am Verify Student and I am writing to express my interest in your PhD group. "
    "Your article on recognition structures is compelling. I have attached my CV.",
    "Yours sincerely,",
    "Verify Student",
])

# 3. planning document (auto-excluded reference)
docx(os.path.join(BASE, "申请时间规划.docx"), [
    "某同学 2028-2029 硕士申请时间规划",
    "2026 年 8 月-2027 年 2 月",
    "• 探索研究方向并形成院校长名单",
    "2027 年 3 月-6 月",
    "• 完成学术 CV 初稿与推荐人沟通",
    "2027 年 7 月-9 月",
    "• 建立导师池并准备 EOI 材料",
])

# 4. unrelated workbook (auto-excluded)
wb = Workbook()
ws = wb.active
ws.title = "any_extracted_results"
ws.append(["Chinese_Source", "English_Translation_Marked", "Collocation"])
for i in range(6):
    ws.append([f"第一千二百{i}条　建筑物倒塌造成他人损害的，应当承担责任。",
               f"Article 12{i} Where a building collapses, liability follows.", "any"])
wb.save(os.path.join(BASE, "未命名电子表格.xlsx"))
wb.close()

# 5. batch csv (recognized but blocked by this import path)
import csv
with open(os.path.join(BASE, "全量56人.csv"), "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["编号", "收件人", "主题", "正文", "附件", "定时时间"])
    writer.writerow(["001", "a@example.edu", "Subject",
                     "Dear Prof. A,\n\nI hope this email finds you well. Letter body.\n\nYours sincerely,\nStudent",
                     "Student-CV.pdf", "2026-08-27 07:30"])
print("written to", BASE)
