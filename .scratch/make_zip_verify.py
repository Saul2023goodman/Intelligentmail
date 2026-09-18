"""Build zip fixtures for browser verification of zip expansion + optional master."""
import os, zipfile
from openpyxl import Workbook

BASE = os.path.join(os.path.dirname(__file__), "verify-zip")
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


# letters-only zip: person-name draft with recipient + planning reference
os.makedirs(BASE, exist_ok=True)
tmp = os.path.join(BASE, "tmp")
os.makedirs(tmp, exist_ok=True)
docx(os.path.join(tmp, "Alex Green.docx"), [
    "Dear Dr Green,",
    "I hope this email finds you well.",
    "I am Verify Student and I am writing to express my interest in your PhD group. "
    "Your article on recognition structures is compelling. I have attached my CV.",
    "Yours sincerely,",
    "Verify Student",
])
docx(os.path.join(tmp, "申请时间规划.docx"), [
    "某同学 2028-2029 硕士申请时间规划",
    "2026 年 8 月-2027 年 2 月", "• 探索研究方向并形成院校长名单",
    "2027 年 3 月-6 月", "• 完成学术 CV 初稿",
    "2027 年 7 月-9 月", "• 建立导师池",
])
with zipfile.ZipFile(os.path.join(BASE, "letters-only.zip"), "w") as z:
    z.write(os.path.join(tmp, "Alex Green.docx"), "Alex Green.docx")
    z.write(os.path.join(tmp, "申请时间规划.docx"), "申请时间规划.docx")

# with-master zip
wb = Workbook(); ws = wb.active; ws.title = "Sheet1"
ws.append(["大学", "导师", "邮箱📮", "URL"])
ws.append(["Example University", "Dr Alex Green", "alex@example.edu", "https://example.edu/alex"])
wb.save(os.path.join(tmp, "master.xlsx")); wb.close()
with zipfile.ZipFile(os.path.join(BASE, "with-master.zip"), "w") as z:
    z.write(os.path.join(tmp, "master.xlsx"), "master.xlsx")
    z.write(os.path.join(tmp, "Alex Green.docx"), "Alex Green.docx")
print("written", os.listdir(BASE))
