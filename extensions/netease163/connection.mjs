export const IDLE_POLL_DELAY_MS = 250;
export const BUSY_POLL_DELAY_MS = 1000;
export const DISCOVERY_RETRY_DELAYS_MS = [500, 1000, 2000, 4000, 8000, 15000];

const MAILBOX_ORIGIN = "https://mail.163.com";
const MAILBOX_PATH = "/js6/main.jsp";

/** Return the single mailbox identity reported by chrome.scripting. */
export function mailboxIdentity(results) {
  if (!Array.isArray(results) || results.length !== 1) return "";
  const value = results[0]?.result;
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

/** Keep command pickup responsive without increasing the busy heartbeat rate. */
export function nextPollDelay(busy) {
  return busy ? BUSY_POLL_DELAY_MS : IDLE_POLL_DELAY_MS;
}

/** A tab is connectable only after the authenticated mailbox document has loaded. */
export function isMailboxTab(tab) {
  if (!tab || typeof tab.id !== "number" || tab.status === "loading") return false;
  try {
    const url = new URL(tab.url || tab.pendingUrl || "");
    return url.origin === MAILBOX_ORIGIN && url.pathname === MAILBOX_PATH;
  } catch {
    return false;
  }
}

/**
 * Pick a tab without guessing between background mailbox accounts.
 * An explicit/preferred tab wins, otherwise one active candidate or the only
 * candidate is safe to select. Ambiguous background tabs require one click.
 */
export function selectMailboxTab(tabs, preferredTabId = null) {
  const eligible = Array.isArray(tabs) ? tabs.filter(isMailboxTab) : [];
  const preferred = eligible.find(tab => tab.id === preferredTabId);
  if (preferred) return preferred;
  const active = eligible.filter(tab => tab.active);
  if (active.length === 1) return active[0];
  return eligible.length === 1 ? eligible[0] : null;
}

export function reconnectDelay(attempt) {
  const index = Math.max(0, Math.min(Number(attempt) || 0, DISCOVERY_RETRY_DELAYS_MS.length - 1));
  return DISCOVERY_RETRY_DELAYS_MS[index];
}
