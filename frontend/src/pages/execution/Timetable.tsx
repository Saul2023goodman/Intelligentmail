import { useRef } from "react";
import {
  cellKey,
  DAY_LABEL,
  SLOT_LABEL,
  type Density,
  type Row,
  type Session,
  type Slot,
  type Tone,
} from "./timetable-model";

const escape = (value: string) => value.replace(/["\\]/g, "\\$&");

/**
 * The institution × session grid: rows are schools, columns are sessions, one cell is
 * one advisor. It is built to stay readable at full campaign scale — sticky headers on
 * both axes, a density switch, a "now" line, and a hover crosshair that makes the
 * school-serial / school-parallel pacing rule visible instead of merely documented.
 */
export default function Timetable({
  sessions,
  rows,
  index,
  tick,
  today,
  nowKey,
  density,
  toneOf,
  onPick,
}: {
  sessions: Session[];
  rows: Row[];
  index: Map<string, Slot>;
  tick: number;
  today: string;
  nowKey: string | null;
  density: Density;
  toneOf: (slot: Slot) => Tone;
  onPick: (slot: Slot) => void;
}) {
  const table = useRef<HTMLTableElement>(null);
  const hot = useRef<{ row: string | null; col: string | null }>({ row: null, col: null });

  /**
   * The crosshair is painted straight onto the DOM. One delegated listener keeps a grid
   * of hundreds of cells from re-rendering on every pointer move.
   */
  function highlight(row: string | null, col: string | null) {
    const previous = hot.current;
    if (previous.row === row && previous.col === col) return;
    const element = table.current;
    if (!element) return;
    for (const node of element.querySelectorAll(".is-row-hot")) node.classList.remove("is-row-hot");
    for (const node of element.querySelectorAll(".is-col-hot")) node.classList.remove("is-col-hot");
    if (row) {
      for (const node of element.querySelectorAll(`[data-row="${escape(row)}"]`)) {
        node.classList.add("is-row-hot");
      }
    }
    if (col) {
      for (const node of element.querySelectorAll(`[data-col="${escape(col)}"]`)) {
        node.classList.add("is-col-hot");
      }
    }
    hot.current = { row, col };
  }

  const bands: { date: string; span: number; weekday: string; today: boolean }[] = [];
  for (const session of sessions) {
    const band = bands[bands.length - 1];
    if (band && band.date === session.date) band.span += 1;
    else {
      bands.push({
        date: session.date,
        span: 1,
        weekday: session.weekday,
        today: session.date === today,
      });
    }
  }
  const showBands = sessions.length !== bands.length;

  return (
    <div className="ex-grid-wrap">
      <table
        ref={table}
        className={`ex-grid is-${density}`}
        onMouseOver={(event) => {
          const cell = (event.target as HTMLElement).closest<HTMLElement>("[data-row],[data-col]");
          if (cell) highlight(cell.dataset.row ?? null, cell.dataset.col ?? null);
        }}
        onMouseLeave={() => highlight(null, null)}
      >
        <thead>
          {showBands && (
            <tr className="ex-bandrow">
              <th className="ex-grid-corner" scope="col">
                <span className="ex-corner-title">院校</span>
              </th>
              {bands.map((band) => (
                <th
                  key={band.date}
                  scope="colgroup"
                  colSpan={band.span}
                  className={`ex-bandhead${band.today ? " is-today" : ""}`}
                >
                  {band.date.slice(5).replace("-", "/")} {DAY_LABEL[band.weekday] ?? ""}
                </th>
              ))}
            </tr>
          )}
          <tr>
            <th className="ex-grid-corner" scope="col">
              <span className="ex-corner-title">{showBands ? "档期" : "院校 / 档期"}</span>
            </th>
            {sessions.map((session) => (
              <th
                key={session.key}
                scope="col"
                data-col={session.key}
                className={[
                  "ex-colhead",
                  session.dayStart ? "is-day-start" : "",
                  session.date === today ? "is-today" : "",
                  session.key === nowKey ? "is-nowline" : "",
                  session.epoch <= tick ? "is-past" : "",
                ].filter(Boolean).join(" ")}
              >
                <span className="ex-col-date">
                  {session.dayStart || !showBands
                    ? `${session.date.slice(5).replace("-", "/")} ${DAY_LABEL[session.weekday] ?? ""}`
                    : DAY_LABEL[session.weekday] ?? ""}
                  {session.date === today && <em className="ex-now-pill">今天</em>}
                  {session.key === nowKey && <em className="ex-now-flag">现在</em>}
                </span>
                <span className="ex-col-window">
                  {session.start && session.end ? `${session.start}–${session.end}` : "档期"}
                </span>
                <span className={`ex-col-count${session.count ? "" : " is-zero"}`}>
                  {session.count}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.institution} data-row={row.institution}>
              <th className="ex-rowhead" scope="row" data-row={row.institution}>
                <span className="ex-row-name" title={row.institution}>{row.institution}</span>
                <span className="ex-row-meta">
                  <span className="ex-row-bar">
                    <i style={{ width: `${row.count ? (row.sent / row.count) * 100 : 0}%` }} />
                  </span>
                  <span className="ex-row-count">{row.sent}/{row.count}</span>
                </span>
              </th>
              {sessions.map((session) => {
                const classes = [
                  "ex-cell",
                  session.dayStart ? "is-day-start" : "",
                  session.epoch <= tick ? "is-past" : "",
                  session.key === nowKey ? "is-nowline" : "",
                ].filter(Boolean).join(" ");
                const slot = index.get(cellKey(row.institution, session.key));
                if (!slot) {
                  return (
                    <td
                      key={session.key}
                      className={classes}
                      data-row={row.institution}
                      data-col={session.key}
                    >
                      <span className="ex-gap" aria-hidden="true"><i>不投</i></span>
                      <span className="ex-sr-only">{row.institution} 该档期不投</span>
                    </td>
                  );
                }
                const tone = toneOf(slot);
                const due = slot.epoch <= tick && tone !== "sent";
                return (
                  <td
                    key={session.key}
                    className={classes}
                    data-row={row.institution}
                    data-col={session.key}
                  >
                    <button
                      type="button"
                      className={`ex-slot is-${tone}${due ? " is-due" : ""}`}
                      title={`${row.institution} · ${slot.supervisor} · ${slot.time}`}
                      aria-label={`${row.institution} ${slot.supervisor}，${session.date} ${slot.time}，${SLOT_LABEL[tone]}`}
                      onClick={() => onPick(slot)}
                    >
                      <span className="ex-slot-head">
                        <span className="ex-slot-time">{slot.time}</span>
                        <i className="ex-slot-dot" />
                      </span>
                      <span className="ex-slot-name">{slot.supervisor}</span>
                      {density === "comfy" && (
                        <span className="ex-slot-state">{SLOT_LABEL[tone]}</span>
                      )}
                      {due && density === "comfy" && <em className="ex-slot-due">已到</em>}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
