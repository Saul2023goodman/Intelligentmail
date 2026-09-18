import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { core } from "../core";
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
  connected: "Mailbox connected",
  mismatch: "Different mailbox connected",
  disconnected: "Gateway disconnected",
  unavailable: "Gateway unavailable",
};

function gatewayNote(
  state: GatewayState,
  student: MailboxSummary,
  connectedAddress: string,
): string {
  if (state === "connected")
    return `${student.student_name}'s mailbox is connected and ready to read.`;
  if (state === "mismatch")
    return `The gateway is connected to ${connectedAddress}. Reconnect ${student.address} in the extension before reading.`;
  if (state === "disconnected")
    return `${student.student_name} is not connected. Connect ${student.address} in the extension before reading.`;
  return "The 163 extension adapter is unavailable. Connect this student's mailbox tab before reading.";
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
  const [deleting, setDeleting] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");
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
      : "Select or add a student to switch the workspace, mailbox, and campaign together.";

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

  const remove = async (mailbox: MailboxSummary) => {
    const confirmed = window.confirm(
      `Permanently delete ${mailbox.student_name} and all locally stored workspace records?\n\nThis cannot be undone. The mailbox account itself will not be changed.`,
    );
    if (!confirmed) return;
    setDeleting(mailbox.student_id);
    setDeleteError("");
    try {
      await core("delete_student", {
        student_id: mailbox.student_id,
        mailbox: mailbox.address,
      });
      const refreshed = await workspaceQuery.refresh();
      if (scope?.studentId === mailbox.student_id) {
        const next = refreshed.mailboxes[0];
        setScope(
          next
            ? {
                studentId: next.student_id,
                studentName: next.student_name,
                mailbox: next.address,
                campaignId: next.campaign_id,
                campaignName:
                  refreshed.campaigns.find(
                    (campaign) => campaign.id === next.campaign_id,
                  )?.name ?? "",
              }
            : null,
        );
      }
      setPreview(null);
    } catch (error) {
      setDeleteError((error as Error).message);
    } finally {
      setDeleting(null);
    }
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
            ? `Current student workspace ${current.student_name} (${current.address}). Switch student`
            : "Select or add a student workspace"
        }
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className="workspace-scope-avatar" aria-hidden="true">
          {scope?.studentName.trim().slice(0, 1).toUpperCase() || "?"}
        </span>
        <span className="workspace-scope-copy">
          <strong>{scope?.studentName || "No student selected"}</strong>
          <small>{scope?.mailbox || "Switch workspace from any page"}</small>
        </span>
        <span
          className={`scope-dot ${currentHealth.state}`}
          aria-hidden="true"
          title={`Mailbox gateway: ${GATEWAY_LABEL[currentHealth.state]}`}
        />
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div
          className="scope-panel"
          role="dialog"
          aria-label="Switch student workspace"
          onKeyDown={moveFocus}
        >
          <div className="scope-current">
            <span className="scope-eyebrow">Current workspace</span>
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
                  <dt>Observation batches</dt>
                  <dd>{current.observation_count}</dd>
                </div>
              </dl>
            ) : (
              <p className="scope-current-empty">No student workspace selected</p>
            )}
            <p className="scope-rule">
              Each student is bound to one mailbox and one Campaign; switching changes all of them together.
            </p>
          </div>
          <label className="scope-search">
            <Icon name="search" size={14} />
            <input
              ref={search}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search student or mailbox"
              aria-label="Search student or mailbox"
            />
          </label>
          <div className="scope-list" role="group" aria-label="Student workspaces">
            {filtered.length === 0 && (
              <p className="scope-empty">No matching student or mailbox</p>
            )}
            {filtered.map((mailbox) => {
              const health = healthOf(mailbox);
              const active = mailbox.student_id === scope?.studentId;
              return (
                <div
                  key={mailbox.id}
                  className={`scope-row${active ? " current" : ""}`}
                  onMouseEnter={() => setPreview(mailbox.student_id)}
                  onMouseLeave={() => setPreview(null)}
                >
                  <button
                    type="button"
                    data-student-row=""
                    className="scope-row-select"
                    aria-current={active ? "true" : undefined}
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
                        <span className="scope-row-current">Current</span>
                      ) : null}
                      <span className={`scope-badge ${health.state}`}>
                        <i aria-hidden="true" />
                        {GATEWAY_LABEL[health.state]}
                      </span>
                      <span className="scope-row-obs">
                        {mailbox.observation_count} observations
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="scope-row-delete"
                    disabled={deleting !== null}
                    aria-label={`Delete ${mailbox.student_name}`}
                    title={`Delete ${mailbox.student_name}`}
                    onClick={() => void remove(mailbox)}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              );
            })}
          </div>
          {deleteError ? (
            <p className="scope-delete-error" role="alert">{deleteError}</p>
          ) : null}
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
              <Icon name="plus" size={14} /> Add student
            </button>
            <button
              type="button"
              className="scope-link"
              onClick={() => {
                close();
                navigate("workflow");
              }}
            >
              Manage mailbox gateway <Icon name="arrow" size={12} />
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
