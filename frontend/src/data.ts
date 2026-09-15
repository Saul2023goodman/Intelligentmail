import type {
  Campaign,
  ExecutionPause,
  EvidenceCoverage,
  MailboxLink,
  NavSection,
  OutreachTask,
  RecordEntry,
} from './domain'

/* ────────────────────────────────────────────────────────────────────────
   Scope
   ──────────────────────────────────────────────────────────────────────── */

export const campaigns: Campaign[] = [
  { id: 'c-2027', name: '2027 秋季外联', meta: '41 名学生 · 52 个在制任务' },
  { id: 'c-2026s', name: '2026 春季补录', meta: '9 名学生 · 已归档' },
]

export const activeCampaignId = 'c-2027'

export const mailboxLink: MailboxLink = {
  address: 'wangyu@163.com',
  state: 'connected',
  student: '王宇',
  lastSync: '09:42',
  capabilities: [
    { id: 'read', label: '只读观测', state: 'verified' },
    { id: 'send_now', label: '立即发送', state: 'verified' },
    { id: 'native_schedule', label: '原生定时', state: 'roadmap' },
    { id: 'schedule_cancel', label: '定时取消', state: 'roadmap' },
    { id: 'scheduled_replacement', label: '定时替换', state: 'roadmap' },
    { id: 'recall', label: '撤回', state: 'roadmap' },
  ],
}

/* ────────────────────────────────────────────────────────────────────────
   Navigation — nine sections from the IA. Only the four numbers that need
   cross-page chasing become queue lights; track counts live on the tracks.
   ──────────────────────────────────────────────────────────────────────── */

export const navSections: NavSection[] = [
  { id: 'console', label: '态势', canonical: 'console', icon: 'grid' },
  { id: 'tasks', label: '任务', canonical: 'tasks', icon: 'stack' },
  {
    id: 'preparation',
    label: '制备',
    canonical: 'preparation',
    icon: 'compose',
    lights: [{ label: '阻断', value: 7, tone: 'alarm' }],
  },
  {
    id: 'plans',
    label: '发送计划',
    canonical: 'plans',
    icon: 'clock',
    lights: [{ label: '待确认', value: 1, tone: 'cool' }],
  },
  {
    id: 'execution',
    label: '执行',
    canonical: 'execution',
    icon: 'play',
    lights: [{ label: '暂停', value: 1, tone: 'alarm' }],
  },
  {
    id: 'mailbox',
    label: '邮箱与对账',
    canonical: 'mailbox',
    icon: 'inbox',
    lights: [{ label: '待核实', value: 2, tone: 'amber' }],
  },
  {
    id: 'replies',
    label: '回复与跟进',
    canonical: 'replies',
    icon: 'reply',
    lights: [{ label: '跟进到期', value: 2, tone: 'amber' }],
  },
  { id: 'reports', label: '报告', canonical: 'reports', icon: 'chart' },
  { id: 'settings', label: '设置', canonical: 'settings', icon: 'sliders' },
]

/* ────────────────────────────────────────────────────────────────────────
   Evidence coverage — the qualifier that must never be separated from the
   "no duplicate found" conclusion it limits.
   ──────────────────────────────────────────────────────────────────────── */

const coverageFull: EvidenceCoverage = {
  folders: [
    { folder: '已发箱', declared: 214, enumerated: 214, pages: 5, pagesTotal: 5 },
    { folder: '收件箱', declared: 148, enumerated: 148, pages: 5, pagesTotal: 5 },
  ],
  blindSpots: [],
}

const coveragePartial: EvidenceCoverage = {
  folders: [
    { folder: '已发箱', declared: 214, enumerated: 214, pages: 5, pagesTotal: 5 },
    { folder: '收件箱', declared: 148, enumerated: 92, pages: 3, pagesTotal: 5 },
  ],
  blindSpots: ['2 个自定义文件夹未覆盖', '虚拟视图「全部邮件」不在支持范围'],
}

const coverageDrafts: EvidenceCoverage = {
  folders: [
    { folder: '已发箱', declared: 214, enumerated: 214, pages: 5, pagesTotal: 5 },
    { folder: '收件箱', declared: 148, enumerated: 148, pages: 5, pagesTotal: 5 },
    { folder: '草稿箱', declared: 6, enumerated: 6, pages: 1, pagesTotal: 1 },
  ],
  blindSpots: ['正文 HTML 未纳入指纹比对'],
}

/* ────────────────────────────────────────────────────────────────────────
   Tasks
   ──────────────────────────────────────────────────────────────────────── */

const LETTER_BODY = `Dear Professor Smith,

I am writing to express my interest in pursuing a PhD under your supervision
from the 2027 intake. I completed my MSc in Supply Chain Management at
Shanghai Jiao Tong University, where my thesis examined multi-echelon
inventory optimisation under demand uncertainty.

Your recent work on resilience in global supply networks — particularly the
2025 paper on disruption propagation in semiconductor sourcing — closely
matches the direction I hope to develop further. During my studies I spent
eleven months as a planning analyst at a contract electronics manufacturer,
where I built the demand-sensing model that is now used for quarterly S&OP.

I have attached my CV and academic transcript. I would be grateful for the
opportunity to discuss whether my background might fit your group, and I am
happy to provide a research proposal outline or further materials.

Thank you for your time and consideration.

Yours sincerely,
Wang Yu
wangyu@163.com`

const FOLLOWUP_BODY = `Dear Professor Patel,

I hope this message finds you well. I wrote to you on 8 September regarding
the possibility of doctoral supervision from the 2027 intake, and I wanted to
follow up in case my earlier note was overlooked.

I remain very interested in your group's work on stochastic optimisation for
humanitarian logistics. My MSc thesis on multi-echelon inventory under
demand uncertainty, together with eleven months of industry experience
building a demand-sensing model now used for quarterly S&OP, would I believe
give me a useful foundation to contribute to that agenda.

I have re-attached my CV and transcript for convenience. I would welcome the
chance to discuss a possible research proposal at any time that suits you.

Thank you again for your consideration.

Yours sincerely,
Wu Qian
wuqian@163.com`

export const tasks: OutreachTask[] = [
  /* ── 待核实 · verify ─────────────────────────────────────────────────
     Unknown outcome and ambiguous links. Hollow, dashed, never red/green.
     The only permitted action is reconcile or adjudicate.               */
  {
    id: 'T-1051',
    stage: 'verify',
    student: '赵琳',
    supervisor: 'R. Patel',
    supervisorAliases: ['r.patel@ntu.edu.sg', 'patel.r@ieee.org'],
    institution: 'Nanyang Technological University',
    mailbox: 'zhaolin@163.com',
    sender: 'zhaolin@163.com',
    recipient: 'r.patel@ntu.edu.sg',
    action: 'initial_outreach',
    status: 'unknown_outcome',
    readiness: 'confirmed',
    duplicate: 'unchecked',
    coverage: coveragePartial,
    reply: 'none',
    followup: {
      eligibility: 'reply_review_required',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'PhD supervision enquiry – Zhao Lin',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_ZhaoLin.pdf',
        bytes: 398_112,
        sha: '4c81f0…9de2',
        state: 'confirmed',
      },
    ],
    blockers: [],
    attempt: {
      id: 'A-1025',
      phase: 'submission',
      note: '提交后跨越观测边界，已发箱未取得唯一匹配证据',
    },
    versions: [{ at: '09:31', text: 'A-1025 提交，未取得回执' }],
    annotation: '结果未知 · 已阻止盲目重试',
  },
  {
    id: 'T-1047',
    stage: 'verify',
    student: '孙浩',
    supervisor: '李萌',
    supervisorAliases: ['limeng@pku.edu.cn'],
    institution: 'Peking University',
    mailbox: 'sunhao@163.com',
    sender: 'sunhao@163.com',
    recipient: 'limeng@pku.edu.cn',
    action: 'initial_outreach',
    status: 'sent',
    readiness: 'confirmed',
    duplicate: 'ambiguous_match',
    coverage: coveragePartial,
    reply: 'ambiguous',
    followup: {
      eligibility: 'reply_review_required',
      waitedDays: 4,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Re: 博士申请咨询 — 孙浩',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_SunHao.pdf',
        bytes: 421_880,
        sha: '77bd40…09a1',
        state: 'confirmed',
      },
    ],
    blockers: [],
    sentRecord: {
      id: 'S-880',
      canonicalId: '163:20260911:8f21c4',
      sentAt: '09-11 10:04',
    },
    versions: [{ at: '09:38', text: '观测到 1 封回复，关联歧义' }],
    annotation: '回复歧义 · 主题线程与地址均可匹配两个任务',
  },

  /* ── 受阻 · blocked ────────────────────────────────────────────────── */
  {
    id: 'T-1042',
    stage: 'blocked',
    student: '王宇',
    supervisor: 'Aaron Smith',
    supervisorAliases: ['a.smith@ntu.edu.sg', 'aaron.smith@ntu.edu.sg'],
    institution: 'Nanyang Technological University',
    mailbox: 'wangyu@163.com',
    sender: 'wangyu@163.com',
    recipient: 'prof.smith@ntu.edu.sg',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'duplicate_suspicion',
    coverage: coveragePartial,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'PhD supervision enquiry – Wang Yu',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_WangYu.pdf',
        bytes: 421_888,
        sha: '9f2ac4…c13',
        state: 'confirmed',
      },
      { id: 'a2', name: '成绩单.pdf', bytes: 0, sha: '', state: 'missing' },
    ],
    blockers: [
      {
        id: 'b1',
        kind: 'recipient_conflict',
        label: '收件人与主管登记地址冲突',
        action: '修正收件人',
        shortcut: 'E',
      },
      {
        id: 'b2',
        kind: 'identity_unconfirmed',
        label: '主管身份未确认',
        action: '确认身份',
        shortcut: 'E',
      },
      {
        id: 'b3',
        kind: 'attachment_missing',
        label: '附件槽位「成绩单」缺失',
        action: '选择文件',
        shortcut: 'A',
      },
    ],
    plannedAt: '09:00',
    revisedFrom: '08:30',
    versions: [
      { at: '09:12', text: '主题已修正（来源：总表 C 列）' },
      { at: '09:13', text: '重新制备 · 生成 v3，v2 转为已被取代' },
    ],
    annotation: '✕3 · 疑似历史联系 · CV 412 KB',
  },
  {
    id: 'T-1044',
    stage: 'blocked',
    student: '陈静',
    supervisor: 'K. Tan',
    supervisorAliases: ['k.tan@nus.edu.sg'],
    institution: 'National University of Singapore',
    mailbox: 'chenjing@163.com',
    sender: 'chenjing@163.com',
    recipient: 'k.tan@nus.edu.sg',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'no_duplicate_found',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Prospective doctoral student — Chen Jing',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_ChenJing.pdf',
        bytes: 366_204,
        sha: '1ae902…77f4',
        state: 'confirmed',
      },
    ],
    blockers: [
      {
        id: 'b1',
        kind: 'identity_unconfirmed',
        label: '主管身份未确认（三个候选地址同源）',
        action: '确认身份',
        shortcut: 'E',
      },
    ],
    versions: [{ at: '08:57', text: '自动制备完成 · v1' }],
    annotation: '✕1 · 身份未确认',
  },
  {
    id: 'T-1060',
    stage: 'blocked',
    student: '刘洋',
    supervisor: 'Ngo Thi Lan',
    supervisorAliases: ['nt.lan@vnu.edu.vn'],
    institution: 'Vietnam National University',
    mailbox: 'liuyang@163.com',
    sender: 'liuyang@163.com',
    recipient: 'nt.lan@vnu.edu.vn',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'unchecked',
    coverage: coveragePartial,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: '',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_LiuYang.pdf',
        bytes: 401_120,
        sha: 'b60f31…2210',
        state: 'advisory',
      },
    ],
    blockers: [
      {
        id: 'b1',
        kind: 'subject_missing',
        label: '主题缺失，源行未提供且不可推断',
        action: '补写主题',
        shortcut: 'E',
      },
      {
        id: 'b2',
        kind: 'rewrite_required',
        label: '学生于 09:20 提交修订版 .docx',
        action: '发起 Rewrite',
        shortcut: 'E',
      },
    ],
    versions: [{ at: '09:20', text: '检测到新材料，需 Rewrite' }],
    annotation: '✕2 · 缺主题 · 待 Rewrite',
  },
  {
    id: 'T-1063',
    stage: 'blocked',
    student: '张沐',
    supervisor: 'M. Okafor',
    supervisorAliases: ['m.okafor@uct.ac.za'],
    institution: 'University of Cape Town',
    mailbox: 'zhangmu@163.com',
    sender: 'zhangmu@163.com',
    recipient: 'm.okafor@uct.ac.za',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'repeat_execution',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Doctoral enquiry — Zhang Mu',
    body: LETTER_BODY,
    attachments: [],
    blockers: [
      {
        id: 'b1',
        kind: 'recipient_conflict',
        label: '重复执行 · 已发箱存在同收件人同主题记录',
        action: '查看匹配证据',
        shortcut: 'R',
      },
    ],
    versions: [{ at: '09:02', text: '查重判定 repeat_execution，硬阻断' }],
    annotation: '✕1 · 重复执行（硬阻断）',
  },
  {
    id: 'T-1066',
    stage: 'blocked',
    student: '周子航',
    supervisor: 'S. Yamamoto',
    supervisorAliases: ['s.yamamoto@u-tokyo.ac.jp'],
    institution: 'The University of Tokyo',
    mailbox: 'zhouzihang@163.com',
    sender: 'zhouzihang@163.com',
    recipient: 's.yamamoto@u-tokyo.ac.jp',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'no_duplicate_found',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Research student enquiry — Zhou Zihang',
    body: LETTER_BODY,
    attachments: [
      { id: 'a1', name: 'CV_ZhouZihang.pdf', bytes: 0, sha: '', state: 'missing' },
      {
        id: 'a2',
        name: 'Research_Proposal.pdf',
        bytes: 812_440,
        sha: 'c2f19a…0b77',
        state: 'advisory',
      },
    ],
    blockers: [
      {
        id: 'b1',
        kind: 'attachment_missing',
        label: '必需附件「CV」缺失',
        action: '选择文件',
        shortcut: 'A',
      },
    ],
    versions: [{ at: '08:44', text: '附件槽位建议 2 项，确认 1 项' }],
    annotation: '✕1 · 缺 CV',
  },
  {
    id: 'T-1069',
    stage: 'blocked',
    student: '黄思远',
    supervisor: 'L. Fernández',
    supervisorAliases: ['l.fernandez@upc.edu'],
    institution: 'Universitat Politècnica de Catalunya',
    mailbox: 'huangsiyuan@163.com',
    sender: 'huangsiyuan@163.com',
    recipient: 'l.fernandez@upc.edu',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'unchecked',
    coverage: coveragePartial,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'PhD application — Huang Siyuan',
    body: LETTER_BODY,
    attachments: [],
    blockers: [
      {
        id: 'b1',
        kind: 'identity_unconfirmed',
        label: '主管身份未确认',
        action: '确认身份',
        shortcut: 'E',
      },
      {
        id: 'b2',
        kind: 'subject_missing',
        label: '收件人域名与登记不一致',
        action: '修正收件人',
        shortcut: 'E',
      },
    ],
    versions: [{ at: '09:26', text: '导入完成，2 项阻断' }],
    annotation: '✕2 · 身份与域名待核',
  },
  {
    id: 'T-1071',
    stage: 'blocked',
    student: '徐若彤',
    supervisor: 'D. Whitfield',
    supervisorAliases: ['d.whitfield@leeds.ac.uk'],
    institution: 'University of Leeds',
    mailbox: 'xuruotong@163.com',
    sender: 'xuruotong@163.com',
    recipient: 'd.whitfield@leeds.ac.uk',
    action: 'follow_up',
    status: 'locally_planned',
    readiness: 'blocked',
    duplicate: 'linked_follow_up',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'due',
      waitedDays: 8,
      intervalDays: 7,
      limit: 2,
      round: 1,
    },
    subject: 'Re: PhD application — Xu Ruotong',
    body: FOLLOWUP_BODY,
    attachments: [
      { id: 'a1', name: 'CV_XuRuotong.pdf', bytes: 0, sha: '', state: 'missing' },
    ],
    blockers: [
      {
        id: 'b1',
        kind: 'attachment_missing',
        label: '跟进模板要求重新附带 CV',
        action: '选择文件',
        shortcut: 'A',
      },
    ],
    versions: [{ at: '09:15', text: '按规则 R-2 自动制备跟进 v1' }],
    annotation: '✕1 · 跟进缺 CV',
  },

  /* ── 就绪待确认 · ready ──────────────────────────────────────────────
     Ready is not authorised. The amber filament lives here.            */
  {
    id: 'T-1055',
    stage: 'ready',
    student: '李明',
    supervisor: '陈伟旺',
    supervisorAliases: ['ww.chen@hkust.edu.hk'],
    institution: 'HKUST',
    mailbox: 'liming@163.com',
    sender: 'liming@163.com',
    recipient: 'ww.chen@hkust.edu.hk',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'ready',
    duplicate: 'no_duplicate_found',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'PhD supervision enquiry – Li Ming',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_LiMing.pdf',
        bytes: 388_920,
        sha: 'e01b7c…44a2',
        state: 'confirmed',
      },
      {
        id: 'a2',
        name: 'Transcript_LiMing.pdf',
        bytes: 295_110,
        sha: '77bd40…09a1',
        state: 'confirmed',
      },
    ],
    blockers: [],
    plannedAt: '09:00',
    versions: [{ at: '08:52', text: '就绪校验通过 · 0 阻断' }],
  },
  {
    id: 'T-1056',
    stage: 'ready',
    student: '吴倩',
    supervisor: 'R. Patel',
    supervisorAliases: ['r.patel@ntu.edu.sg'],
    institution: 'Nanyang Technological University',
    mailbox: 'wuqian@163.com',
    sender: 'wuqian@163.com',
    recipient: 'r.patel@ntu.edu.sg',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'ready',
    duplicate: 'no_duplicate_found',
    coverage: coverageDrafts,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Prospective PhD student — Wu Qian',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_WuQian.pdf',
        bytes: 402_771,
        sha: '3ff20d…8c19',
        state: 'confirmed',
      },
    ],
    blockers: [],
    plannedAt: '10:00',
    versions: [{ at: '08:55', text: '就绪校验通过 · 0 阻断' }],
  },
  {
    id: 'T-1058',
    stage: 'ready',
    student: '马晓东',
    supervisor: 'H. Bergström',
    supervisorAliases: ['h.bergstrom@kth.se'],
    institution: 'KTH Royal Institute of Technology',
    mailbox: 'maxiaodong@163.com',
    sender: 'maxiaodong@163.com',
    recipient: 'h.bergstrom@kth.se',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'ready',
    duplicate: 'no_duplicate_found',
    coverage: coveragePartial,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'Doctoral studies enquiry — Ma Xiaodong',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_MaXiaodong.pdf',
        bytes: 351_004,
        sha: '9a41be…0f55',
        state: 'confirmed',
      },
    ],
    blockers: [],
    versions: [{ at: '09:07', text: '歧义匹配已裁决为 no_duplicate_found' }],
    annotation: '查重已裁决 · 覆盖度存在缺口',
  },

  /* ── 已确认 · confirmed ───────────────────────────────────────────── */
  ...confirmedBand(),

  /* ── 执行中 · executing ───────────────────────────────────────────── */
  {
    id: 'T-1050',
    stage: 'executing',
    student: '何嘉怡',
    supervisor: 'A. Kowalski',
    supervisorAliases: ['a.kowalski@ethz.ch'],
    institution: 'ETH Zürich',
    mailbox: 'hejiayi@163.com',
    sender: 'hejiayi@163.com',
    recipient: 'a.kowalski@ethz.ch',
    action: 'initial_outreach',
    status: 'locally_planned',
    readiness: 'confirmed',
    duplicate: 'no_duplicate_found',
    coverage: coverageFull,
    reply: 'none',
    followup: {
      eligibility: 'no_initial_send',
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: 'PhD enquiry — He Jiayi',
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: 'CV_HeJiayi.pdf',
        bytes: 377_401,
        sha: '5d20cc…a1f8',
        state: 'confirmed',
      },
    ],
    blockers: [],
    attempt: { id: 'A-1026', phase: 'submission', note: '正在提交，等待已发箱证据' },
    versions: [{ at: '09:41', text: 'A-1026 进入 submission 阶段' }],
    annotation: 'A-1026 · submission',
  },

  /* ── 已发送 · sent ────────────────────────────────────────────────── */
  ...sentBand(),

  /* ── 跟进中 · followup ────────────────────────────────────────────── */
  ...followupBand(),
]

function confirmedBand(): OutreachTask[] {
  const rows: [string, string, string, string, string, string, string][] = [
    ['T-1057', '郑一帆', 'J. Marchetti', 'j.marchetti@polimi.it', 'Politecnico di Milano', '09:00', 'zhengyifan@163.com'],
    ['T-1059', '林澈', 'P. Raghunathan', 'p.raghunathan@iitm.ac.in', 'IIT Madras', '11:00', 'linche@163.com'],
    ['T-1061', '高雨桐', 'E. Lindqvist', 'e.lindqvist@lu.se', 'Lund University', '', 'gaoyutong@163.com'],
    ['T-1062', '谢明轩', 'C. Delacroix', 'c.delacroix@ethz.ch', 'ETH Zürich', '14:00', 'xiemingxuan@163.com'],
    ['T-1064', '罗清和', '张文博', 'wb.zhang@tsinghua.edu.cn', 'Tsinghua University', '15:00', 'luoqinghe@163.com'],
    ['T-1065', '韩雪', 'N. Abdi', 'n.abdi@tudelft.nl', 'TU Delft', '', 'hanxue@163.com'],
  ]
  return rows.map(([id, student, supervisor, recipient, institution, plannedAt, mailbox], i) => ({
    id,
    stage: 'confirmed' as const,
    student,
    supervisor,
    supervisorAliases: [recipient],
    institution,
    mailbox,
    sender: mailbox,
    recipient,
    action: 'initial_outreach' as const,
    status: 'locally_planned' as const,
    readiness: 'confirmed' as const,
    duplicate: 'no_duplicate_found' as const,
    coverage: coverageFull,
    reply: 'none' as const,
    followup: {
      eligibility: 'no_initial_send' as const,
      waitedDays: 0,
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: `PhD supervision enquiry – ${student}`,
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: `CV_${id}.pdf`,
        bytes: 340_000 + i * 18_412,
        sha: `${(i + 2).toString(16)}f2ac4…c1${i}`,
        state: 'confirmed' as const,
      },
    ],
    blockers: [],
    plannedAt: plannedAt || undefined,
    versions: [{ at: `09:${10 + i}`, text: 'Confirmation 已绑定摘要' }],
  }))
}

function sentBand(): OutreachTask[] {
  const rows: [string, string, string, string, string, string][] = [
    ['T-1004', '王宇', 'A. Smith', 'a.smith@ntu.edu.sg', '09-08 09:00', '163:20260908:1a2b3c'],
    ['T-1006', '李明', '陈伟旺', 'ww.chen@hkust.edu.hk', '09-08 10:00', '163:20260908:4d5e6f'],
    ['T-1009', '吴倩', 'R. Patel', 'r.patel@ntu.edu.sg', '09-09 09:00', '163:20260909:7a8b9c'],
    ['T-1011', '赵琳', 'M. Okafor', 'm.okafor@uct.ac.za', '09-09 10:00', '163:20260909:0d1e2f'],
    ['T-1013', '孙浩', 'S. Yamamoto', 's.yamamoto@u-tokyo.ac.jp', '09-09 11:00', '163:20260909:3a4b5c'],
    ['T-1015', '陈静', 'L. Fernández', 'l.fernandez@upc.edu', '09-10 09:00', '163:20260910:6d7e8f'],
    ['T-1017', '刘洋', 'D. Whitfield', 'd.whitfield@leeds.ac.uk', '09-10 10:00', '163:20260910:9a0b1c'],
    ['T-1019', '张沐', 'H. Bergström', 'h.bergstrom@kth.se', '09-10 14:00', '163:20260910:2d3e4f'],
    ['T-1021', '周子航', 'A. Kowalski', 'a.kowalski@ethz.ch', '09-11 09:00', '163:20260911:5a6b7c'],
    ['T-1023', '黄思远', 'J. Marchetti', 'j.marchetti@polimi.it', '09-11 10:00', '163:20260911:8d9e0f'],
    ['T-1025', '徐若彤', 'P. Raghunathan', 'p.raghunathan@iitm.ac.in', '09-11 11:00', '163:20260911:1a2c3d'],
    ['T-1027', '马晓东', 'E. Lindqvist', 'e.lindqvist@lu.se', '09-12 09:00', '163:20260912:4e5f6a'],
    ['T-1029', '何嘉怡', 'C. Delacroix', 'c.delacroix@ethz.ch', '09-12 10:00', '163:20260912:7b8c9d'],
    ['T-1031', '郑一帆', '张文博', 'wb.zhang@tsinghua.edu.cn', '09-12 14:00', '163:20260912:0e1f2a'],
    ['T-1033', '林澈', 'N. Abdi', 'n.abdi@tudelft.nl', '09-13 09:00', '163:20260913:3b4c5d'],
    ['T-1035', '高雨桐', 'T. Halvorsen', 't.halvorsen@ntnu.no', '09-13 10:00', '163:20260913:6e7f8a'],
    ['T-1037', '谢明轩', 'R. Krishnan', 'r.krishnan@nus.edu.sg', '09-13 11:00', '163:20260913:9b0c1d'],
    ['T-1039', '罗清和', 'K. Tan', 'k.tan@nus.edu.sg', '09-14 09:00', '163:20260914:2e3f4a'],
    ['T-1040', '韩雪', '李萌', 'limeng@pku.edu.cn', '09-14 10:00', '163:20260914:5b6c7d'],
    ['T-1041', '唐立', 'Ngo Thi Lan', 'nt.lan@vnu.edu.vn', '09-14 14:00', '163:20260914:8e9f0a'],
    ['T-1043', '王宇', 'K. Tan', 'k.tan@nus.edu.sg', '09-14 15:00', '163:20260914:1b2c3d'],
    ['T-1045', '李明', '李萌', 'limeng@pku.edu.cn', '09-15 09:00', '163:20260915:4e5f6a'],
    ['T-1046', '吴倩', 'Ngo Thi Lan', 'nt.lan@vnu.edu.vn', '09-15 09:20', '163:20260915:7b8c9d'],
    ['T-1048', '赵琳', 'T. Halvorsen', 't.halvorsen@ntnu.no', '09-15 09:31', '163:20260915:0e1f2a'],
    ['T-1049', '孙浩', 'R. Krishnan', 'r.krishnan@nus.edu.sg', '09-15 09:34', '163:20260915:3b4c5d'],
    ['T-1052', '陈静', 'A. Smith', 'a.smith@ntu.edu.sg', '09-15 09:36', '163:20260915:6e7f8a'],
    ['T-1053', '刘洋', '陈伟旺', 'ww.chen@hkust.edu.hk', '09-15 09:38', '163:20260915:9b0c1d'],
    ['T-1054', '张沐', 'R. Patel', 'r.patel@ntu.edu.sg', '09-15 09:40', '163:20260915:2e3f4a'],
  ]
  return rows.map(([id, student, supervisor, recipient, sentAt, canonicalId], i) => ({
    id,
    stage: 'sent' as const,
    student,
    supervisor,
    supervisorAliases: [recipient],
    institution: recipient.split('@')[1] ?? '',
    mailbox: `${student.toLowerCase()}@163.com`,
    sender: `${student.toLowerCase()}@163.com`,
    recipient,
    action: 'initial_outreach' as const,
    status: 'sent' as const,
    readiness: 'confirmed' as const,
    duplicate: 'no_duplicate_found' as const,
    coverage: coverageFull,
    reply: i === 3 ? ('associated' as const) : ('none' as const),
    followup: {
      eligibility: (i === 3 ? 'ordinary_reply_received' : 'waiting') as OutreachTask['followup']['eligibility'],
      waitedDays: i === 3 ? 0 : 7 - (i % 7),
      intervalDays: 7,
      limit: 2,
      round: 0,
    },
    subject: `PhD supervision enquiry – ${student}`,
    body: LETTER_BODY,
    attachments: [
      {
        id: 'a1',
        name: `CV_${id}.pdf`,
        bytes: 320_000 + i * 12_900,
        sha: `${(i % 9) + 1}f2ac4…c1${i % 10}`,
        state: 'confirmed' as const,
      },
    ],
    blockers: [],
    sentRecord: { id: `S-${860 + i}`, canonicalId, sentAt },
    versions: [{ at: sentAt, text: `已发箱唯一匹配 · 冻结 S-${860 + i}` }],
  }))
}

function followupBand(): OutreachTask[] {
  const rows: [string, string, string, string, number, OutreachTask['followup']['eligibility'], string][] = [
    ['T-1030', '周子航', 'A. Kowalski', 'a.kowalski@ethz.ch', 8, 'due', ''],
    ['T-1032', '黄思远', 'J. Marchetti', 'j.marchetti@polimi.it', 9, 'due', ''],
    ['T-1034', '徐若彤', 'P. Raghunathan', 'p.raghunathan@iitm.ac.in', 3, 'waiting', ''],
    ['T-1036', '马晓东', 'E. Lindqvist', 'e.lindqvist@lu.se', 5, 'waiting', ''],
    ['T-1038', '郑一帆', '张文博', 'wb.zhang@tsinghua.edu.cn', 12, 'maximum_reached', ''],
  ]
  return rows.map(([id, student, supervisor, recipient, waitedDays, eligibility, note], i) => ({
    id,
    stage: 'followup' as const,
    student,
    supervisor,
    supervisorAliases: [recipient],
    institution: recipient.split('@')[1] ?? '',
    mailbox: `${student.toLowerCase()}@163.com`,
    sender: `${student.toLowerCase()}@163.com`,
    recipient,
    action: 'follow_up' as const,
    status: 'sent' as const,
    readiness: 'ready' as const,
    duplicate: 'linked_follow_up' as const,
    coverage: coverageFull,
    reply: 'none' as const,
    followup: { eligibility, waitedDays, intervalDays: 7, limit: 2, round: 1 },
    subject: `Re: PhD supervision enquiry – ${student}`,
    body: FOLLOWUP_BODY,
    attachments: [
      {
        id: 'a1',
        name: `CV_${id}.pdf`,
        bytes: 340_000 + i * 9_120,
        sha: `${i + 3}f2ac4…c1${i}`,
        state: 'confirmed' as const,
      },
    ],
    blockers: [],
    versions: [{ at: `09:${18 + i}`, text: `跟进资格 ${eligibility}` }],
    annotation:
      eligibility === 'due'
        ? `已等待 ${waitedDays} 天 · 待制备${note}`
        : eligibility === 'waiting'
          ? `等待第 ${waitedDays} 天 / 间隔 7 天`
          : '已达跟进上限 2 次',
  }))
}

/* ────────────────────────────────────────────────────────────────────────
   Stage definitions — order is risk order, sent sinks to the bottom.
   ──────────────────────────────────────────────────────────────────────── */

export interface StageMeta {
  id: OutreachTask['stage']
  label: string
  canonical: string
  semantic: string
  action: string
  shortcut: string
  signal: 'unknown' | 'alarm' | 'amber' | 'cool' | 'verified' | 'mute'
}

export const stages: StageMeta[] = [
  {
    id: 'verify',
    label: '待核实',
    canonical: 'verify',
    semantic: '证据不足，需对账或人工判定',
    action: '对账 / 裁决',
    shortcut: 'R',
    signal: 'unknown',
  },
  {
    id: 'blocked',
    label: '受阻',
    canonical: 'blocked',
    semantic: '存在阻断项，未就绪',
    action: '就地修正',
    shortcut: 'E',
    signal: 'alarm',
  },
  {
    id: 'ready',
    label: '就绪待确认',
    canonical: 'ready',
    semantic: '就绪不等于授权',
    action: '确认发送',
    shortcut: 'C',
    signal: 'amber',
  },
  {
    id: 'confirmed',
    label: '已确认',
    canonical: 'confirmed',
    semantic: '授权已绑定，等待或正在执行',
    action: '查看许可',
    shortcut: '',
    signal: 'cool',
  },
  {
    id: 'executing',
    label: '执行中',
    canonical: 'executing',
    semantic: '三阶段证据在检查栏内联展开',
    action: '查看证据',
    shortcut: '',
    signal: 'cool',
  },
  {
    id: 'sent',
    label: '已发送',
    canonical: 'sent',
    semantic: '已发箱证据证实，记录不可变',
    action: '只读',
    shortcut: '',
    signal: 'verified',
  },
  {
    id: 'followup',
    label: '跟进中',
    canonical: 'followup',
    semantic: '等待计时 / 已到期待制备',
    action: '制备跟进',
    shortcut: 'C',
    signal: 'amber',
  },
]

/* ────────────────────────────────────────────────────────────────────────
   Execution pause — one reason, one valid primary action.
   ──────────────────────────────────────────────────────────────────────── */

export const executionPauses: ExecutionPause[] = [
  {
    id: 'p1',
    attempt: 'A-1025',
    taskId: 'T-1051',
    reason: 'unknown_outcome',
    reasonLabel: '结果未知',
    fact: '提交后跨越观测边界，已发箱未取得唯一匹配证据',
    prevented: '已阻止盲目重试',
    primary: '立即对账',
    secondary: '记录人工接管',
  },
]

/* ────────────────────────────────────────────────────────────────────────
   Record stream — the single global event ledger. Nothing else duplicates it.
   ──────────────────────────────────────────────────────────────────────── */

export const recordStream: RecordEntry[] = [
  {
    id: 'r1',
    at: '09:42',
    channel: 'observation',
    text: '观测同步完成 · 3 条新观测，1 条未关联',
    tone: 'neutral',
    link: 'mailbox/observations',
  },
  {
    id: 'r2',
    at: '09:40',
    channel: 'execution',
    text: 'A-1024 已发送 · S-901 · T-1054',
    tone: 'verified',
    link: 'execution/sent/S-901',
  },
  {
    id: 'r3',
    at: '09:38',
    channel: 'execution',
    text: 'A-1025 提交后结果未知 · Execution Flow 已暂停',
    tone: 'unknown',
    link: 'execution/attempts/A-1025',
  },
  {
    id: 'r4',
    at: '09:36',
    channel: 'reply',
    text: '观测到 1 封回复，关联歧义 · T-1047',
    tone: 'neutral',
    link: 'replies/ambiguous',
  },
  {
    id: 'r5',
    at: '09:31',
    channel: 'confirmation',
    text: 'Confirmation C-771 绑定摘要 · T-1050',
    tone: 'neutral',
    link: 'execution/confirmations/C-771',
  },
  {
    id: 'r6',
    at: '09:26',
    channel: 'import',
    text: '导入批次 I-038 · 12 行成功关联，2 项 findings',
    tone: 'neutral',
    link: 'imports/I-038',
  },
  {
    id: 'r7',
    at: '09:20',
    channel: 'preparation',
    text: 'T-1060 检测到修订版材料 · 需 Rewrite',
    tone: 'alarm',
    link: 'preparation/T-1060',
  },
  {
    id: 'r8',
    at: '09:15',
    channel: 'preparation',
    text: 'T-1071 按规则 R-2 自动制备跟进 v1',
    tone: 'neutral',
    link: 'preparation/T-1071',
  },
  {
    id: 'r9',
    at: '09:13',
    channel: 'preparation',
    text: 'T-1042 重新制备 · v3 生效，v2 转为已被取代',
    tone: 'neutral',
    link: 'preparation/T-1042/history',
  },
  {
    id: 'r10',
    at: '09:12',
    channel: 'preparation',
    text: 'T-1042 主题已修正 · 来源：总表 C 列',
    tone: 'neutral',
    link: 'preparation/T-1042',
  },
  {
    id: 'r11',
    at: '09:07',
    channel: 'reconciliation',
    text: 'T-1058 歧义匹配已裁决为未发现重复',
    tone: 'verified',
    link: 'mailbox/duplicates/T-1058',
  },
  {
    id: 'r12',
    at: '09:02',
    channel: 'reconciliation',
    text: 'T-1063 查重判定 repeat_execution · 硬阻断',
    tone: 'alarm',
    link: 'mailbox/duplicates/T-1063',
  },
  {
    id: 'r13',
    at: '08:57',
    channel: 'preparation',
    text: '自动制备完成 · 41 份制备，7 项阻断',
    tone: 'neutral',
    link: 'preparation',
  },
  {
    id: 'r14',
    at: '08:44',
    channel: 'import',
    text: '导入批次 I-037 · 29 行成功关联，0 项 findings',
    tone: 'verified',
    link: 'imports/I-037',
  },
]

/* ────────────────────────────────────────────────────────────────────────
   Sending plan — next slot only. The full timetable lives on /plans.
   ──────────────────────────────────────────────────────────────────────── */

export const nextPlanSlot = {
  planId: 7,
  at: '10:00',
  date: '09-15',
  taskId: 'T-1056',
  constraints: 'Asia/Shanghai · 周一至五 09:00–17:00 · 间隔 60′ · 日上限 2',
  pendingConfirm: 1,
}

export const operator = { name: '林岚', initials: 'LL' }
