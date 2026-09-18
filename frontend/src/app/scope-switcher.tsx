import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useCoreQuery } from "../core/data";
import { gatewayHealth, type GatewayState } from "../core/gateway";
import type { MailboxSummary } from "../core";
import { navigate } from "./routes";
import { useWorkspaceScope } from "./scope";
import { StudentDialog } from "./student-dialog";
import Icon from "../shared/Icon";
import "./scope-switcher.css";

/* oxlint-disable react/only-export-components -- The switcher and its labels form one shared shell control. */

const NO_MAILBOXES: MailboxSummary[] = [];

/** Gateway state as it concerns one Student's mailbox, before switching. */
const GATEWAY_LABEL: Record<GatewayState, string> = {
  connected: "邮箱已连接",
  mismatch: "连着其他邮箱",
  disconnected: "网关未连接",
  unavailable: "网关未启用",
};

function gatewayNote(
  state: GatewayState,
  student: MailboxSummary,
  connectedAddress: string,
): string {
  if (state === "connected")
    return `${student.student_name} 的邮箱已连接，切换后可直接读取证据。`;
  if (state === "mismatch")
    return `网关当前连着 ${connectedAddress}，切换后读取前需在扩展中重连 ${student.address}。`;
  if (state === "disconnected")
    return `${student.student_name} 尚未连接网关，切换后需在扩展中连接 ${student.address} 再读取。`;
  return "未启用 163 扩展适配器，读取邮箱前需先连接该学生的邮箱标签页。";
}

function initials(name: string): string {
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "?";
}

/**
 * The global workspace switcher. One Student owns one mailbox and one
 * Campaign, so switching is a single deliberate act across the whole shell:
 * the trigger shows who is active, the panel shows what switching will cost
 * (gateway connection) before it happens.
 */
export function ScopeSwitcher() {
  const { scope, setScope } = useWorkspaceScope();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);

  const workspaceQuery = useCoreQuery("workspace", {});
  const gatewayQuery = useCoreQuery("gateway_status", {}, {
    maxAge: 1_000,
    refetchInterval: open ? 3_000 : 0,
  });
  const data = workspaceQuery.data;
  const gateway = gatewayQuery.data ?? data?.mailbox_capabilities.gateway;
  const mailboxes = data?.mailboxes ?? NO_MAILBOXES;

  const healthOf = useCallback(
    (mailbox: MailboxSummary | null) => gatewayHealth(gateway, mailbox),
    [gateway],
  );

  const current =
    mailboxes.find((mailbox) => mailbox.student_id === scope?.studentId) ?? null;
  const currentHealth = healthOf(current);
  const campaignName =
    data?.campaigns.find((campaign) => campaign.id === current?.campaign_id)
      ?.name ?? scope?.campaignName ?? "";

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return mailboxes;
    return mailboxes.filter(
      (mailbox) =>
        mailbox.student_name.toLowerCase().includes(needle) ||
        mailbox.address.toLowerCase().includes(needle),
    );
  }, [mailboxes, query]);

  const previewed =
    (preview && mailboxes.find((mailbox) => mailbox.student_id === preview)) ||
    null;
  const note = previewed
    ? gatewayNote(
        healthOf(previewed).state,
        previewed,
        healthOf(previewed).connectedAddress,
      )
    : current
      ? gatewayNote(currentHealth.state, current, currentHealth.connectedAddress)
      : "选择或新增一位学生，工作区、邮箱与 Campaign 会一起切换。";

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = () => {
    setOpen(false);
    setQuery("");
    setPreview(null);
  };

  const select = (mailbox: MailboxSummary) => {
    setScope({
      studentId: mailbox.student_id,
      studentName: mailbox.student_name,
      mailbox: mailbox.address,
      campaignId: mailbox.campaign_id,
      campaignName:
        data?.campaigns.find((campaign) => campaign.id === mailbox.campaign_id)
          ?.name ?? "",
    });
    close();
  };

  const moveFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const rows = Array.from(
      root.current?.querySelectorAll<HTMLButtonElement>("[data-student-row]") ??
        [],
    );
    if (!rows.length) return;
    event.preventDefault();
    const index = rows.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "ArrowDown"
        ? rows[Math.min(index + 1, rows.length - 1)]
        : rows[Math.max(index - 1, 0)];
    (index === -1 ? rows[0] : next)?.focus();
  };

  return (
    <div className="scope-switcher" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="workspace-scope-indicator"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={
          current
            ? `当前学生工作区 ${current.student_name}（${current.address}）。切换学生`
            : "选择或新增学生工作区"
        }
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className="workspace-scope-avatar" aria-hidden="true">
          {scope?.studentName.trim().slice(0, 1).toUpperCase() || "?"}
        </span>
        <span className="workspace-scope-copy">
          <strong>{scope?.studentName || "尚未选择学生"}</strong>
          <small>{scope?.mailbox || "在任意页面切换工作区"}</small>
        </span>
        <span
          className={`scope-dot ${currentHealth.state}`}
          aria-hidden="true"
          title={`邮箱网关：${GATEWAY_LABEL[currentHealth.state]}`}
        />
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div
          className="scope-panel"
          role="dialog"
          aria-label="切换学生工作区"
          onKeyDown={moveFocus}
        >
          <div className="scope-current">
            <span className="scope-eyebrow">当前工作区</span>
            {current ? (
              <dl>
                <div>
                  <dt>Student</dt>
                  <dd>{current.student_name}</dd>
                </div>
                <div>
                  <dt>Mailbox</dt>
                  <dd>{current.address}</dd>
                </div>
                <div>
                  <dt>Campaign</dt>
                  <dd>{campaignName || "—"}</dd>
                </div>
                <div>
                  <dt>读取批次</dt>
                  <dd>{current.observation_count}</dd>
                </div>
              </dl>
            ) : (
              <p className="scope-current-empty">尚未选择学生工作区</p>
            )}
            <p className="scope-rule">
              一位学生绑定一个邮箱与一个 Campaign，切换即整体切换。
            </p>
          </div>
          <label className="scope-search">
            <Icon name="search" size={14} />
            <input
              ref={search}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索学生或邮箱"
              aria-label="搜索学生或邮箱"
            />
          </label>
          <div className="scope-list" role="group" aria-label="学生工作区">
            {filtered.length === 0 && (
              <p className="scope-empty">没有匹配的学生或邮箱</p>
            )}
            {filtered.map((mailbox) => {
              const health = healthOf(mailbox);
              const active = mailbox.student_id === scope?.studentId;
              return (
                <button
                  key={mailbox.id}
                  type="button"
                  data-student-row=""
                  className={`scope-row${active ? " current" : ""}`}
                  aria-current={active ? "true" : undefined}
                  onMouseEnter={() => setPreview(mailbox.student_id)}
                  onMouseLeave={() => setPreview(null)}
                  onFocus={() => setPreview(mailbox.student_id)}
                  onClick={() => select(mailbox)}
                >
                  <span className="scope-row-avatar" aria-hidden="true">
                    {initials(mailbox.student_name)}
                  </span>
                  <span className="scope-row-copy">
                    <strong>{mailbox.student_name}</strong>
                    <small>{mailbox.address}</small>
                  </span>
                  <span className="scope-row-meta">
                    {active ? (
                      <span className="scope-row-current">当前</span>
                    ) : null}
                    <span className={`scope-badge ${health.state}`}>
                      <i aria-hidden="true" />
                      {GATEWAY_LABEL[health.state]}
                    </span>
                    <span className="scope-row-obs">
                      {mailbox.observation_count} 次读取
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          <p className="scope-note">{note}</p>
          <div className="scope-footer">
            <button
              type="button"
              className="scope-create"
              onClick={() => {
                close();
                setCreating(true);
              }}
            >
              <Icon name="plus" size={14} /> 新增学生
            </button>
            <button
              type="button"
              className="scope-link"
              onClick={() => {
                close();
                navigate("workflow");
              }}
            >
              管理邮箱网关 <Icon name="arrow" size={12} />
            </button>
          </div>
        </div>
      )}
      <StudentDialog
        open={creating}
        onClose={() => setCreating(false)}
      />
    </div>
  );
}
