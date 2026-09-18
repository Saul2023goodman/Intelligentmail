import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { core } from "../core";
import { useWorkspaceScope } from "./scope";
import Icon from "../shared/Icon";
import "./student-dialog.css";

/**
 * One dialog for creating a Student workspace, shared by the global scope
 * switcher and the Workflow empty state. Core owns the creation rules; the
 * dialog only collects the name and mailbox, then selects the new workspace.
 */
export function StudentDialog({
  open,
  onClose,
  onCreated,
  intro,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (student: { id: string; name: string; mailbox: string }) => void;
  intro?: ReactNode;
}) {
  const { setScope } = useWorkspaceScope();
  const [name, setName] = useState("");
  const [mailboxAddress, setMailboxAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const modal = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    // oxlint-disable-next-line react/set-state-in-effect -- Reset the form each time the dialog opens.
    setError("");
    const previous = document.activeElement as HTMLElement | null;
    const element = modal.current;
    const focusable = () =>
      Array.from(
        element?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, [tabindex="0"]',
        ) ?? [],
      );
    (element?.querySelector<HTMLInputElement>("input") ?? focusable()[0])?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const targets = focusable();
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    element?.addEventListener("keydown", trap);
    return () => {
      element?.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;

  const close = () => {
    setName("");
    setMailboxAddress("");
    setError("");
    onClose();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = await core("create_student", {
        name: name.trim(),
        mailbox: mailboxAddress.trim(),
      });
      setScope({
        studentId: value.id,
        studentName: value.name,
        mailbox: value.mailbox,
        campaignId: value.campaign_id,
        campaignName: "",
      });
      setName("");
      setMailboxAddress("");
      onCreated?.(value);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="student-dialog-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        ref={modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="student-dialog-title"
        className="student-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
        }}
      >
        <button
          className="modal-close icon-button"
          aria-label="Close dialog"
          onClick={close}
        >
          <Icon name="close" />
        </button>
        <form onSubmit={submit}>
          <div className="eyebrow">STUDENT WORKSPACE</div>
          <h2 id="student-dialog-title">Set up student</h2>
          <p>
            {intro ??
              "Each student is bound to one sending mailbox and one Campaign. Observation, reconciliation & duplicate check, and follow-up all happen inside that student's workspace."}
          </p>
          <label className="field">
            Student name
            <input
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Zhang Wei"
            />
          </label>
          <label className="field">
            163 mailbox address
            <input
              required
              type="email"
              maxLength={200}
              value={mailboxAddress}
              onChange={(event) => setMailboxAddress(event.target.value)}
              placeholder="student@163.com"
            />
          </label>
          {error && (
            <p role="alert" className="finding">
              {error}
            </p>
          )}
          <button
            className="primary full"
            disabled={busy || !name.trim() || !mailboxAddress.trim()}
          >
            {busy ? "Adding…" : "Add student"}
            <Icon name="arrow" size={16} />
          </button>
        </form>
      </section>
    </div>
  );
}
