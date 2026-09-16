import { useState } from "react";
import type { Detail } from "../../core";
import { core } from "../../core";

export default function DraftEditor({
  preparation,
  sources,
  onSaved,
}: {
  preparation: Detail["preparations"][number];
  sources: Detail["rewrite_sources"];
  onSaved: () => Promise<void>;
}) {
  const [subject, setSubject] = useState(preparation.subject);
  const [recipient, setRecipient] = useState(preparation.recipient);
  const [sourceId, setSourceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const save = async (rewrite: boolean) => {
    setBusy(true);
    setError("");
    setResult("");
    try {
      if (rewrite) {
        await core("rewrite", {
          preparation_id: preparation.id,
          source_id: sourceId.trim(),
        });
      } else {
        await core("update_preparation", {
          preparation_id: preparation.id,
          subject,
          recipient,
        });
      }
      setResult("已保存并重新校验。内容变更需要重新确认；发送前请重新查重。");
      await onSaved();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="draft-editor">
      <summary>更新 / 调整本地草稿</summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save(false);
        }}
      >
        <label className="field">
          收件人
          <input
            type="email"
            required
            value={recipient}
            disabled={busy}
            onChange={(e) => setRecipient(e.target.value)}
          />
        </label>
        <label className="field">
          主题
          <input
            required
            maxLength={1000}
            value={subject}
            disabled={busy}
            onChange={(e) => setSubject(e.target.value)}
          />
        </label>
        <button
          className="secondary full"
          disabled={busy || !subject.trim() || !recipient.trim()}
        >
          保存并重新校验
        </button>
      </form>
      <p className="muted">
        此操作修改 SmartMail 本地
        Preparation，不覆盖外部邮箱草稿。已发送或尚未解决的外部操作由 Core
        阻止修改。
      </p>
      <div className="section-label">正文替换 / REWRITE</div>
      <p className="muted">
        先导入修订文档，再选择替换来源。Core
        验证任务匹配，创建新版本并保留旧版本，旧确认不继承。
      </p>
      <p className="muted">当前来源：{preparation.source.name}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save(true);
        }}
      >
        <label className="field">
          替换来源文档
          <select
            required
            value={sourceId}
            disabled={busy}
            onChange={(e) => setSourceId(e.target.value)}
          >
            <option value="">选择已导入的修订文档</option>
            {sources.map((source, index) => (
              <option key={source.id} value={source.id}>
                {source.name} · 材料 {index + 1}
                {source.id === preparation.source.id ? "（当前来源）" : ""}
              </option>
            ))}
          </select>
        </label>
        <button className="secondary full" disabled={busy || !sourceId.trim()}>
          从文档创建新版本
        </button>
      </form>
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
    </details>
  );
}
