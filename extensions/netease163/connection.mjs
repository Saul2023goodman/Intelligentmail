export const IDLE_POLL_DELAY_MS = 250;
export const BUSY_POLL_DELAY_MS = 1000;

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
