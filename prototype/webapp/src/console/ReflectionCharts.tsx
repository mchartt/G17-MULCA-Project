// The Reflection page's small charts (Matteo, 20/11: "un po' di colore, anche
// grafici"). Plain SVG and CSS, no chart library. Group-level only: counts of
// the group's messages and tasks, never who. Each chart carries its numbers as
// text (a legend, a label or a hidden table), so colour is never the only cue.
// Status colours (validated with the dataviz checks): done --ok, in progress
// --act, waiting --wn, to do --ag-solid.
import type { Task } from "./plan";
import { waitingOn } from "./plan";

const DAY = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" });
const LONG_DAY = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

/** How much of the whole plan is done: a ring, with the number beside it. */
export function ProgressRing({ done, total }: { done: number; total: number }) {
  const share = total ? done / total : 0;
  const r = 26;
  const length = 2 * Math.PI * r;
  return (
    <div className="ring">
      <svg viewBox="0 0 64 64" width="64" height="64" role="img" aria-label={`${Math.round(share * 100)}% of the plan done: ${done} of ${total} tasks`}>
        <circle cx="32" cy="32" r={r} className="ring__track" />
        {done > 0 && (
          <circle cx="32" cy="32" r={r} className="ring__value" strokeDasharray={`${share * length} ${length}`} transform="rotate(-90 32 32)" />
        )}
      </svg>
      <div>
        <span className="stat__value">{Math.round(share * 100)}%</span>
        <span className="stat__label">of the plan done ({done} of {total})</span>
      </div>
    </div>
  );
}

type Day = { day: string; messages: number; done: number };

/** One small column chart over the seven days; the same day axis for every measure (no dual axis). */
function Columns({ days, measure, label, today }: { days: Day[]; measure: "messages" | "done"; label: string; today: string }) {
  const top = Math.max(1, ...days.map((d) => d[measure]));
  const total = days.reduce((sum, d) => sum + d[measure], 0);
  return (
    <figure className={`cols cols--${measure}`}>
      <figcaption className="cols__head">
        <span>{label}</span>
        <strong className="cols__total">{total}</strong>
      </figcaption>
      {total === 0 && <p className="cols__empty muted small">None this week.</p>}
      <ol className="cols__plot" aria-hidden="true">
        {days.map((d) => (
          <li key={d.day} className={d.day === today ? "cols__day cols__day--today" : "cols__day"} title={`${LONG_DAY(d.day)}: ${d[measure]} ${label.toLowerCase()}`}>
            {d[measure] > 0 && <span className="cols__n">{d[measure]}</span>}
            <span className="cols__bar" style={{ height: d[measure] ? `${Math.max(6, (d[measure] / top) * 80)}%` : 0 }} />
          </li>
        ))}
      </ol>
      <ol className="cols__axis" aria-hidden="true">
        {days.map((d) => <li key={d.day} className={d.day === today ? "cols__today" : undefined}>{DAY(d.day)}</li>)}
      </ol>
    </figure>
  );
}

/** The week day by day: messages, then tasks done, as small multiples; a table for screen readers. */
export function WeekByDay({ days, today }: { days: Day[]; today: string }) {
  return (
    <div className="byday">
      <Columns days={days} measure="messages" label="Messages" today={today} />
      <Columns days={days} measure="done" label="Tasks done" today={today} />
      <table className="sr-only">
        <caption>The week day by day</caption>
        <thead><tr><th scope="col">Day</th><th scope="col">Messages</th><th scope="col">Tasks done</th></tr></thead>
        <tbody>{days.map((d) => <tr key={d.day}><th scope="row">{LONG_DAY(d.day)}</th><td>{d.messages}</td><td>{d.done}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

const STATUSES = [
  { key: "done", label: "Done" },
  { key: "doing", label: "In progress" },
  { key: "waiting", label: "Waiting" },
  { key: "todo", label: "To do" },
] as const;

/** The plan right now, by status: one stacked bar and a legend with the counts. */
export function PlanStatus({ tasks }: { tasks: Task[] }) {
  const waiting = new Set(waitingOn(tasks).filter((w) => w.waiting).map((w) => w.task.task_id));
  const count = { done: 0, doing: 0, waiting: 0, todo: 0 };
  for (const t of tasks) {
    if (t.status === "done") count.done += 1;
    else if (t.status === "blocked" || waiting.has(t.task_id)) count.waiting += 1;
    else if (t.status === "doing") count.doing += 1;
    else count.todo += 1;
  }
  const total = tasks.length;
  if (!total) return <p className="muted small">No tasks in the plan yet.</p>;
  return (
    <div className="status">
      <div className="status__bar" role="img" aria-label={STATUSES.map((s) => `${count[s.key]} ${s.label.toLowerCase()}`).join(", ")}>
        {STATUSES.filter((s) => count[s.key]).map((s) => (
          <span key={s.key} className={`status__seg status__seg--${s.key}`} style={{ flexGrow: count[s.key] }} title={`${s.label}: ${count[s.key]}`} />
        ))}
      </div>
      <ul className="status__legend">
        {STATUSES.map((s) => (
          <li key={s.key}><span className={`status__key status__seg--${s.key}`} aria-hidden="true" />{s.label} <strong>{count[s.key]}</strong></li>
        ))}
      </ul>
    </div>
  );
}

/** Where the group talked: one bar per channel, the count written beside it. */
export function ChannelBars({ talk, names }: { talk: { channel: string; messages: number }[]; names: Record<string, string> }) {
  const top = Math.max(1, ...talk.map((t) => t.messages));
  return (
    <ul className="chan">
      {talk.map((t) => (
        <li key={t.channel}>
          <span className="chan__name">{names[t.channel] ?? t.channel}</span>
          <span className="chan__track" aria-hidden="true"><span className="chan__bar" style={{ width: t.messages ? `${Math.max(3, (t.messages / top) * 100)}%` : 0 }} /></span>
          <span className="chan__n">{t.messages} message{t.messages === 1 ? "" : "s"}</span>
        </li>
      ))}
    </ul>
  );
}
