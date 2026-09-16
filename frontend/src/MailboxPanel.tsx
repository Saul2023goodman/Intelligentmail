import { useEffect, useState } from "react";
import { core, human } from "./core";
import type { MailboxHistory, Workspace } from "./core";
import Icon from "./Icon";

export default function MailboxPanel({
  data,
  onRefresh,
}: {
  data: Workspace;
  onRefresh: () => Promise<void>;
}) {
  const [studentId, setStudentId] = useState(
    data.mailboxes[0]?.student_id || "",
  );
  const [history, setHistory] = useState<MailboxHistory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [version, setVersion] = useState(0);
  const [runId, setRunId] = useState("");
  const observedId = data.mailboxes.find(
    (mailbox) => mailbox.student_id === studentId,
  )?.latest?.id;
  const capability = data.mailbox_capabilities.capabilities.read_history;
  useEffect(() => {
    let active = true;
    if (studentId)
      core<MailboxHistory>("mailbox_history", { student_id: studentId }).then(
        (value) => {
          if (active) setHistory(value);
        },
        (failure) => {
          if (active) setError(failure.message);
        },
      );
    return () => {
      active = false;
    };
  }, [studentId, version, observedId]);
  const refresh = async () => {
    setBusy(true);
    setError("");
    setResult("");
    try {
      const value = await core<{
        observation: { status: string; messages: unknown[]; detail: string };
      }>("refresh_mailbox", { student_id: studentId });
      setResult(
        `读取结果：${human(value.observation.status)} · ${value.observation.messages.length} 条观察记录。${value.observation.detail}`,
      );
      setVersion((v) => v + 1);
      setRunId("");
      await onRefresh();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const latest =
    history?.observations.find((run) => run.id === runId) ??
    history?.observations.at(-1);
  const reconciliation = history?.reconciliations.find(
    (r) => r.observation_id === latest?.id,
  );
  return (
    <section className="mailbox-panel">
      <div className="section-label">外部邮箱 / 本地证据</div>
      <p className="muted">
        按学生邮箱读取；保存的历史供各 Campaign 在各自范围内比对，不会自动创建
        Outreach Task。
      </p>
      {data.mailboxes.length ? (
        <label className="field">
          学生邮箱
          <select
            aria-label="学生邮箱"
            value={studentId}
            disabled={busy}
            onChange={(e) => {
              setStudentId(e.target.value);
              setHistory(null);
              setRunId("");
              setError("");
              setResult("");
            }}
          >
            {data.mailboxes.map((mailbox) => (
              <option key={mailbox.id} value={mailbox.student_id}>
                {mailbox.student_name} · {mailbox.address}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="finding">
          请先通过 Core
          注册学生及其邮箱。读取后可保存观察记录；任务关联仍需明确导入材料。
        </p>
      )}
      <button
        className="secondary full"
        disabled={busy || !studentId || !capability.available}
        onClick={() => void refresh()}
      >
        <Icon name="refresh" size={16} />
        {busy ? "读取并保存中…" : "读取外部邮箱并入库"}
      </button>
      <p className="muted">
        {capability.available
          ? "扩展已连接。请确保选中的已登录 163 标签页与学生邮箱一致。"
          : "请在已登录的 163 邮箱标签页连接 SmartMail 扩展，然后刷新页面。"}
      </p>
      {capability.available && !capability.verified && (
        <p className="muted">
          扩展读取能力尚未完成真实邮箱验收；覆盖范围以每次读取结果为准。
        </p>
      )}
      {error && (
        <p className="finding" role="alert">
          {error}
        </p>
      )}
      {result && (
        <p className="evidence" role="status">
          {result}
        </p>
      )}
      <div className="section-label">
        已保存的读取批次 <span>{history?.observations.length ?? "—"}</span>
      </div>
      {latest ? (
        <>
          <label className="field">
            查看读取批次
            <select
              value={latest.id}
              onChange={(e) => setRunId(e.target.value)}
            >
              {history?.observations.map((run, index) => (
                <option key={run.id} value={run.id}>
                  批次 {index + 1} ·{" "}
                  {new Date(run.observed_at).toLocaleString()} ·{" "}
                  {human(run.status)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            所选批次：{new Date(latest.observed_at).toLocaleString()} ·{" "}
            {human(latest.status)}
          </p>
          <p className="finding">
            证据覆盖：
            {latest.evidence_coverage.complete
              ? "本次声明范围完整"
              : "部分范围，未发现重复不等于没有历史发送"}
            。列表元数据不会覆盖本地草稿正文。
          </p>
          <div className="section-label">
            所选批次 · 邮件观察 <span>{latest.messages.length}</span>
          </div>
          {latest.messages.map((message) => (
            <article className="evidence" key={message.id}>
              <h3>{message.subject || "（无主题）"}</h3>
              <p>{message.counterpart}</p>
              <p>
                {message.folder} · {human(message.status)}
              </p>
            </article>
          ))}
          {!latest.messages.length && (
            <p className="muted">
              本次未取得邮件；之前的读取批次仍保留在数据库。
            </p>
          )}
          <div className="section-label">CORE 比对发现</div>
          {reconciliation?.findings.map((finding) => (
            <article className="evidence" key={finding.id}>
              <h3>{human(finding.finding)}</h3>
              <p>{finding.detail}</p>
            </article>
          ))}
        </>
      ) : (
        <p className="muted">尚无已保存的邮箱观察记录。</p>
      )}
    </section>
  );
}
