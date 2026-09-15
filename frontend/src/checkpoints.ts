import type { OutreachTask } from './domain'

export type CheckState = 'pass' | 'fail' | 'pending' | 'na'
export const stateLabels: Record<CheckState, string> = { pass: '通过', fail: '未通过', pending: '待核实', na: '不适用' }
export const stateMarks: Record<CheckState, string> = { pass: '✓', fail: '×', pending: '·', na: '—' }
export const mainCheckpoints = [
  { id: 'imported', label: '导入', ids: ['record', 'scope'] },
  { id: 'materials', label: '素材通过', ids: ['content', 'attachments'] },
  { id: 'validated', label: '核验通过', ids: ['identity', 'duplicate', 'followup'] },
  { id: 'prepared', label: '发送准备', ids: ['timing', 'confirmation'] },
  { id: 'successful', label: '发送成功', ids: ['receipt', 'archive'] },
] as const
export type MainCheckId = typeof mainCheckpoints[number]['id']
export type FilterId = CheckId | MainCheckId
export const checkpoints = [
  { id: 'record', label: '任务入库', hint: '已建立可追踪的任务记录' },
  { id: 'scope', label: '任务归属', hint: '当前活动下的学生、主管和邮箱归属' },
  { id: 'identity', label: '联系对象', hint: '合并身份、邮箱归属与收件地址的一致性判断' },
  { id: 'content', label: '邮件内容', hint: '主题、正文与当前制备版本' },
  { id: 'attachments', label: '附件', hint: '已选文件是否确认；建议附件不构成发送阻断' },
  { id: 'duplicate', label: '重复风险', hint: '区分同一行动重复执行和初邮重复嫌疑；结论受证据覆盖范围限制' },
  { id: 'followup', label: '跟进资格', hint: '仅跟进适用：回复、等待时间、次数与当前行动' },
  { id: 'timing', label: '发送时间', hint: '仅定时适用；有提议时间不代表约束已验证' },
  { id: 'receipt', label: '发送回执', hint: '以邮箱发送证据为准，结果未知保持待核实' },
  { id: 'archive', label: '记录留存', hint: '已发送内容与附件的留存记录' },
  { id: 'confirmation', label: '发送许可', hint: '当前内容与执行细节的独立授权；不代表已经发送' },
] as const
export type CheckId = typeof checkpoints[number]['id']
export interface CheckResult { state: CheckState; detail: string }

// Independent predicates, never inferred from a position along a workflow.
// Missing evidence stays pending. This frontend uses demonstration records.
export function evaluate(task: OutreachTask): Record<CheckId, CheckResult> {
  const has = (...kinds: string[]) => task.blockers.some(b => kinds.includes(b.kind))
  const result = (state: CheckState, detail: string): CheckResult => ({ state, detail })
  const follow = task.followup
  const identityFailed = has('recipient_conflict', 'identity_unconfirmed') || task.sender !== task.mailbox
  const identityKnown = !!task.sender && !!task.recipient && task.supervisorAliases.includes(task.recipient)
  const followState: CheckState = task.action !== 'follow_up' ? 'na'
    : task.reply === 'ambiguous' || follow.eligibility === 'reply_review_required' ? 'pending'
    : task.reply === 'associated' || ['ordinary_reply_received', 'maximum_reached'].includes(follow.eligibility) ? 'fail'
    : follow.eligibility === 'due' && follow.waitedDays >= follow.intervalDays && follow.round <= follow.limit ? 'pass' : 'pending'
  return {
    record: result(task.id ? 'pass' : 'pending', '任务已建立，可通过编号追踪'),
    scope: result(task.student && task.supervisor && task.mailbox ? 'pass' : 'pending', '当前活动中的学生、主管与邮箱已登记'),
    receipt: result(task.sentRecord?.canonicalId ? 'pass' : task.status === 'observed_failure' ? 'fail' : 'pending', task.sentRecord?.canonicalId ? '已取得邮箱发送记录：' + task.sentRecord.canonicalId : task.status === 'unknown_outcome' ? '发送结果未知，需要对账取得证据' : task.status === 'observed_failure' ? '观测到发送失败' : '尚未取得发送成功回执'),
    archive: result(task.sentRecord?.id ? 'pass' : 'pending', task.sentRecord ? '已留存发送记录 ' + task.sentRecord.id : '发送成功后保留发送内容和附件记录'),
    identity: result(identityFailed ? 'fail' : identityKnown ? 'pass' : 'pending', identityFailed ? '身份或收件地址冲突，请核对关联证据' : identityKnown ? '学生邮箱与已知主管地址一致' : '缺少明确的邮箱归属或主管地址关联证据'),
    content: result(has('subject_missing', 'rewrite_required') || !task.subject.trim() || !task.body.trim() ? 'fail' : 'pass', has('rewrite_required') ? '修订版本需要重新制备' : !task.subject.trim() ? '缺少权威主题' : '检查当前主题、正文与版本'),
    attachments: result(!task.attachments.length ? 'na' : task.attachments.every(a => a.state === 'confirmed' && a.sha && a.bytes > 0) ? 'pass' : 'pending', '仅已确认文件纳入发送内容；未确认建议不作为阻断'),
    duplicate: result(task.duplicate === 'repeat_execution' || task.duplicate === 'duplicate_suspicion' ? 'fail' : task.duplicate === 'unchecked' || task.duplicate === 'ambiguous_match' ? 'pending' : 'pass', task.duplicate === 'repeat_execution' ? '同一行动已经执行，禁止再次发送' : task.duplicate === 'duplicate_suspicion' ? '发现历史外联匹配，需要复核' : task.duplicate === 'linked_follow_up' ? '已链接跟进行动，不属于重复初邮' : `仅依据已检查历史；${task.coverage.blindSpots.join('；') || '不保证覆盖整个邮箱'}`),
    followup: result(followState, task.action !== 'follow_up' ? '本行为初邮，跟进资格不适用' : `第 ${follow.round} 轮 · 已等待 ${follow.waitedDays} / ${follow.intervalDays} 天；普通回复停止资格，自动回复不停止`),
    timing: result(task.plannedAt ? 'pending' : 'na', task.plannedAt ? `${task.plannedAt} · 仍需验证窗口、时区、间隔与日上限` : '立即发送，无定时约束'),
    confirmation: result(task.sentRecord ? 'na' : task.readiness === 'confirmed' ? 'pass' : 'pending', task.sentRecord ? '该行动已发送，许可已消费；历史可查看' : task.readiness === 'confirmed' ? '记录显示已确认；执行前仍需复核有效性' : '尚未获得当前制备的发送许可'),
  }
}

export function evaluateMain(checks: Record<CheckId, CheckResult>): Record<MainCheckId, CheckResult> {
  return Object.fromEntries(mainCheckpoints.map(main => {
    const children = main.ids.map(id => checks[id])
    const applicable = children.filter(c => c.state !== 'na')
    const state: CheckState = children.some(c => c.state === 'fail') ? 'fail'
      : !applicable.length ? 'na' : applicable.some(c => c.state === 'pending') ? 'pending' : 'pass'
    return [main.id, { state, detail: main.ids.map(id => `${checkpoints.find(c => c.id === id)!.label}：${stateLabels[checks[id].state]}`).join('；') }]
  })) as Record<MainCheckId, CheckResult>
}
