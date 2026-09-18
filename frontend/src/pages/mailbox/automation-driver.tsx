import { useEffect, useRef } from "react";
import { useWorkspaceScope } from "../../app/scope";
import { core } from "../../core";

/**
 * The desktop app is the local scheduler host. Core remains the authority:
 * this driver only asks one idempotent interface to evaluate the selected Campaign.
 */
export default function FollowUpAutomationDriver() {
  const { scope } = useWorkspaceScope();
  const campaignId = scope?.campaignId ?? "";
  const active = useRef(false);

  useEffect(() => {
    if (!campaignId) return;
    let disposed = false;
    const process = async () => {
      if (disposed || active.current) return;
      active.current = true;
      try {
        await core("followup_process", { campaign_id: campaignId });
      } catch {
        // The Follow-up workspace exposes the persisted blocker. A background
        // driver must never turn an unavailable mailbox into an unhandled error.
      } finally {
        active.current = false;
      }
    };
    void process();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void process();
    }, 30_000);
    window.addEventListener("focus", process);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", process);
    };
  }, [campaignId]);

  return null;
}
