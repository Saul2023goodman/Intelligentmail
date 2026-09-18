"""Why does one Word file holding several letters still not split?"""

from smartmail.recognition import recognize_bytes
from tests.test_recognition import docx_bytes

BODY = ("I hope this email finds you well. I am Shen Hui, with a Master's degree in "
        "Industrial Design Engineering. I am writing to express my interest in joining "
        "your research group. Your work on diffusion-based camera calibration offers a "
        "compelling approach. I have attached my CV.")
BODY_CN = ("您好！我叫沈慧，目前在某大学攻读工业设计工程硕士学位，正在准备 2027 年秋季入学的博士申请。"
           "我对您在扩散模型标定方向的研究非常感兴趣，希望有机会在您的指导下攻读博士学位。"
           "随信附上我的个人简历，恳请您拨冗指正。")

CASES = {
    "A English, dash heading": [
        "Alex Green — Example University",
        "Email: alex@example.edu",
        "Dear Professor Green,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
        "Blair Blue — Other University",
        "Email: blair@example.edu",
        "Dear Professor Blue,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
    ],
    "B Chinese salutation (no space)": [
        "张教授 — 北京大学",
        "邮箱：zhang@pku.edu.cn",
        "尊敬的张教授：",
        BODY_CN,
        "此致",
        "敬礼",
        "沈慧",
        "李教授 — 清华大学",
        "邮箱：li@tsinghua.edu.cn",
        "尊敬的李教授：",
        BODY_CN,
        "此致",
        "敬礼",
        "沈慧",
    ],
    "C Chinese heading, no dash": [
        "北京大学 张教授",
        "邮箱：zhang@pku.edu.cn",
        "Dear Professor Zhang,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
        "清华大学 李教授",
        "邮箱：li@tsinghua.edu.cn",
        "Dear Professor Li,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
    ],
    "D numbered separator only": [
        "1.",
        "Dear Professor Zhang,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
        "2.",
        "Dear Professor Li,",
        BODY,
        "Yours sincerely,",
        "Shen Hui",
    ],
    "E mixed: english salutation, chinese body": [
        "北京大学 张教授",
        "邮箱：zhang@pku.edu.cn",
        "Dear Professor Zhang,",
        BODY_CN,
        "Yours sincerely,",
        "沈慧",
        "清华大学 李教授",
        "邮箱：li@tsinghua.edu.cn",
        "Dear Professor Li,",
        BODY_CN,
        "Yours sincerely,",
        "沈慧",
    ],
}

for label, paragraphs in CASES.items():
    result = recognize_bytes("letters.docx", docx_bytes(paragraphs))
    segments = result.get("segments") or []
    print(f"\n=== {label}")
    print(f"  type={result['type']}  confidence={result['confidence']}  segments={len(segments)}")
    for index, segment in enumerate(segments, 1):
        print(f"   {index}. supervisor={segment['supervisor']!r} institution={segment['institution']!r} "
              f"salutation={segment['salutation_name']!r} emails={segment['emails']}")
    for caution in result["cautions"]:
        print("   !", caution)
