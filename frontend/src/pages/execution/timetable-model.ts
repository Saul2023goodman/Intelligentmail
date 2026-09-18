import type { PlanConfiguration, Proposal, SendingPlan } from "../../core";

const WEEKDAY_TOKEN: Record<string, string> = {
  Sun: "SUN", Mon: "MON", Tue: "TUE", Wed: "WED", Thu: "THU", Fri: "FRI", Sat: "SAT",
};
export const DAY_LABEL: Record<string, string> = {
  SUN: "周日", MON: "周一", TUE: "周二", WED: "周三", THU: "周四", FRI: "周五", SAT: "周六",
};
export { WEEKDAY_TOKEN };

/** Cell tones are read from mailbox evidence and queue state, never inferred. */
export type Tone =
  | "proposed"
  | "queued"
  | "placed"
  | "sending"
  | "sent"
  | "failed"
  | "unknown"
  | "expired";
export const SLOT_LABEL: Record<Tone, string> = {
  proposed: "已排期",
  queued: "已入队",
  placed: "已投放",
  sending: "发送中",
  sent: "已发送",
  failed: "发送失败",
  unknown: "待对账",
  expired: "需改期",
};
/** Rendering density. Wider grids need narrower columns to stay readable. */
export type Density = "comfy" | "compact" | "micro";
export const DENSITIES: { key: Density; label: string; hint: string }[] = [
  { key: "comfy", label: "宽松", hint: "完整状态文字" },
  { key: "compact", label: "紧凑", hint: "状态用色点" },
  { key: "micro", label: "超密", hint: "最大列数" },
];

/** One planned action placed in the institution × session grid. */
export type Slot = {
  proposal: Proposal;
  institution: string;
  supervisor: string;
  at: string;
  time: string;
  date: string;
  weekday: string;
  session: number | null;
  epoch: number;
};
/** One occurrence of a configured window on one day — the grid's column. */
export type Session = {
  key: string;
  date: string;
  weekday: string;
  index: number | null;
  start: string;
  end: string;
  epoch: number;
  /** Planned actions in this session; zero is a deliberate gap, not missing data. */
  count: number;
  /** True on the first session of a day, drawn with a heavier rule. */
  dayStart: boolean;
};
export type Row = { institution: string; count: number; first: number; sent: number };

export function zoned(
  instant: Date,
  timezone: string,
  options: Intl.DateTimeFormatOptions,
  locale = "en-CA",
) {
  return new Intl.DateTimeFormat(locale, { timeZone: timezone, ...options }).format(instant);
}
/** Milliseconds the zone is ahead of UTC at one instant; used to place wall-clock times. */
function zoneOffset(instant: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(instant);
  const at = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return Date.UTC(
    at("year"), at("month") - 1, at("day"), at("hour") % 24, at("minute"), at("second"),
  ) - instant.getTime();
}
function zonedEpoch(date: string, time: string, timezone: string) {
  const wall = Date.parse(`${date}T${time || "00:00"}:00Z`);
  return wall - zoneOffset(new Date(wall), timezone);
}
function sessionIndex(token: string, time: string, windows: PlanConfiguration["windows"]) {
  for (let index = 0; index < windows.length; index += 1) {
    const window = windows[index];
    if (window.days.includes(token) && window.start <= time && time <= window.end) return index;
  }
  return null;
}

export function buildSlots(plan: SendingPlan | undefined): Slot[] {
  if (!plan) return [];
  const timezone = plan.configuration.timezone;
  return plan.proposals.map((proposal) => {
    const instant = new Date(proposal.scheduled_at);
    const weekday = zoned(instant, timezone, { weekday: "short" }, "en-US");
    const time = zoned(instant, timezone, {
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }, "en-GB");
    const token = WEEKDAY_TOKEN[weekday] ?? "";
    return {
      proposal,
      institution: proposal.institution_name || "Unassigned institution",
      supervisor: proposal.supervisor_name || "Supervisor",
      at: proposal.scheduled_at,
      time,
      date: zoned(instant, timezone, { year: "numeric", month: "2-digit", day: "2-digit" }),
      weekday: token,
      session: sessionIndex(token, time, plan.configuration.windows),
      epoch: instant.getTime(),
    };
  });
}
/**
 * The full session axis. Derived from the plan's own slots, then widened with every
 * configured window falling between the first and last planned day, so a skipped day
 * reads as a deliberate empty column instead of a hole in the timeline.
 */
export function buildSessions(slots: Slot[], configuration: PlanConfiguration): Session[] {
  const found = new Map<string, Session>();
  const windows = configuration?.windows ?? [];
  for (const slot of slots) {
    const key = `${slot.date}#${slot.session ?? "-"}`;
    const window = slot.session === null ? undefined : windows[slot.session];
    const existing = found.get(key);
    if (existing) {
      existing.epoch = Math.min(existing.epoch, slot.epoch);
      continue;
    }
    found.set(key, {
      key,
      date: slot.date,
      weekday: slot.weekday,
      index: slot.session,
      start: window?.start ?? "",
      end: window?.end ?? "",
      epoch: slot.epoch,
      count: 0,
      dayStart: false,
    });
  }
  const dates = [...new Set(slots.map((slot) => slot.date))].sort();
  if (windows.length && dates.length > 1) {
    const unplaced = new Set(
      [...found.keys()].filter((key) => key.endsWith("#-")).map((key) => key.slice(0, 10)),
    );
    const last = dates[dates.length - 1];
    for (let walk = dates[0]; walk <= last;) {
      if (!unplaced.has(walk)) {
        const weekday = WEEKDAY_TOKEN[
          zoned(new Date(`${walk}T12:00:00Z`), configuration.timezone, {
            weekday: "short",
          }, "en-US")
        ] ?? "";
        windows.forEach((window, index) => {
          if (!window.days.includes(weekday)) return;
          const key = `${walk}#${index}`;
          if (found.has(key)) return;
          found.set(key, {
            key,
            date: walk,
            weekday,
            index,
            start: window.start,
            end: window.end,
            epoch: zonedEpoch(walk, window.start, configuration.timezone),
            count: 0,
            dayStart: false,
          });
        });
      }
      walk = new Date(Date.parse(`${walk}T12:00:00Z`) + 86400000).toISOString().slice(0, 10);
    }
  }
  const counts = new Map<string, number>();
  for (const slot of slots) {
    const key = `${slot.date}#${slot.session ?? "-"}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const list = [...found.values()].sort(
    (a, b) => a.epoch - b.epoch || (a.index ?? -1) - (b.index ?? -1),
  );
  let previous = "";
  for (const session of list) {
    session.count = counts.get(session.key) ?? 0;
    session.dayStart = session.date !== previous;
    previous = session.date;
  }
  return list;
}
export function buildRows(slots: Slot[], toneOf: (slot: Slot) => Tone): Row[] {
  const found = new Map<string, Row>();
  for (const slot of slots) {
    const sent = toneOf(slot) === "sent" ? 1 : 0;
    const row = found.get(slot.institution);
    if (row) {
      row.count += 1;
      row.first = Math.min(row.first, slot.epoch);
      row.sent += sent;
      continue;
    }
    found.set(slot.institution, {
      institution: slot.institution,
      count: 1,
      first: slot.epoch,
      sent,
    });
  }
  return [...found.values()].sort((a, b) => a.first - b.first);
}
export const cellKey = (institution: string, session: string) => `${institution}@${session}`;
/** O(1) lookup, so painting an institution × session grid never rescans the slot list. */
export function buildIndex(slots: Slot[]) {
  const index = new Map<string, Slot>();
  for (const slot of slots) {
    index.set(cellKey(slot.institution, `${slot.date}#${slot.session ?? "-"}`), slot);
  }
  return index;
}
/** Dense grids start dense; the operator can still open them up. */
export function autoDensity(sessions: number, rows: number): Density {
  if (sessions > 16 || rows > 12) return "micro";
  if (sessions > 9 || rows > 7) return "compact";
  return "comfy";
}
