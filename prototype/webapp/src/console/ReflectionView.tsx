// Reflection (Matteo, 20/11): how the group worked in one week. The numbers
// and lists come from the plan and the chat (the server's "reflection"
// command); only "What you talked about" is written by Cadence, from the
// week's chat. Everything is about the group, never about one person: no
// per-member counts (the privacy promise: Cadence never scores or ranks people).
import { Capped } from "./Capped";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState } from "react";
import { faBookmark, faChevronLeft, faChevronRight, faCircleCheck, faComments, faFlag } from "../lib/icons";
import { ChannelBars, PlanStatus, ProgressRing, WeekByDay } from "./ReflectionCharts";
import type { MemberId, ProjectState, Reflection } from "../lib/types";
import { dayLabel } from "./plan";

const CHANNELS: Record<string, string> = { web: "Web chat", discord: "Discord", slack: "Slack" };

const mondayOf = (iso: string) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
};
const shift = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
const span = (from: string, to: string) =>
  `${new Date(`${from}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })} – ${new Date(`${to}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;

type Props = {
  state: ProjectState | null;
  today: string;
  nameOf: (id?: MemberId | null) => string | undefined;
  onLoad: (week: string) => Promise<Reflection | string>;
};

/**
 * One task with who owns it and by when. A missing owner or date is shown as such, in the warning
 * colour: it is the gap Cadence exists to close, so the week's review should not hide it.
 */
function TaskLine({ task, today, nameOf, withDate = true }: { task: { task_id: string; title: string; owner_id?: MemberId | null; due_date?: string | null }; today: string; nameOf: Props["nameOf"]; withDate?: boolean }) {
  const owner = task.owner_id ? nameOf(task.owner_id) : undefined;
  const late = !!task.due_date && task.due_date < today;
  return (
    <li className="rtask">
      <span className="rtask__title">{task.title}</span>
      <span className="rtask__meta">
        <span className={owner ? "rtask__who" : "rtask__who rtask__gap"}>
          <span className="rtask__avatar" aria-hidden="true">{owner ? owner.slice(0, 1).toUpperCase() : "?"}</span>
          {owner ?? "No owner"}
        </span>
        {withDate && (
          <span className={task.due_date ? (late ? "due due--late" : "due") : "due rtask__gap"}>
            {task.due_date ? `${late ? "Was due" : "Due"} ${dayLabel(task.due_date)}` : "No deadline"}
          </span>
        )}
      </span>
    </li>
  );
}

export function ReflectionPage({ state, today, nameOf, onLoad }: Props) {
  const [week, setWeek] = useState(() => mondayOf(today));
  const [data, setData] = useState<Reflection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const current = week === mondayOf(today);
  // The parent passes a new function at every render: asking again each time would make the
  // server refuse ("already looking") and drop the answer. Ask once per week shown.
  const load = useRef(onLoad);
  load.current = onLoad;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    void load.current(week).then((answer) => {
      if (!alive) return;
      if (typeof answer === "string") setError(answer);
      else setData(answer);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [week]);

  const shown = data && data.week === week ? data : null;
  const messages = shown?.talk.reduce((sum, t) => sum + t.messages, 0) ?? 0;
  const gaps = shown?.added.filter((t) => !t.owner_id || !t.due_date).length ?? 0;

  return (
    <section className="page reflection-page" aria-label="Reflection" aria-busy={loading}>
      <header className="page__head reflection__head">
        <div className="week" role="group" aria-label="Week">
          <button className="btn btn--soft btn--round" aria-label="Previous week" onClick={() => setWeek(shift(week, -7))}><FontAwesomeIcon icon={faChevronLeft} /></button>
          <p className="week__label"><strong>{current ? "This week" : "Week of"}</strong> <span className="muted">{span(week, shift(week, 6))}</span></p>
          <button className="btn btn--soft btn--round" aria-label="Next week" disabled={current} onClick={() => setWeek(shift(week, 7))}><FontAwesomeIcon icon={faChevronRight} /></button>
        </div>
        <p className="muted small">About the group, never about one person.</p>
      </header>

      {error && <p className="banner banner--warn" role="alert">{error}</p>}
      {!shown && !error && <p className="muted" role="status">Cadence is looking at the week…</p>}

      {shown && (
        <>
          <ul className="stats" aria-label="The week in numbers">
            <li className="stat stat--done"><span className="stat__icon" aria-hidden="true"><FontAwesomeIcon icon={faCircleCheck} /></span><span className="stat__value">{shown.done.length}</span><span className="stat__label">tasks done</span></li>
            <li className="stat stat--decided"><span className="stat__icon" aria-hidden="true"><FontAwesomeIcon icon={faBookmark} /></span><span className="stat__value">{shown.decisions.length}</span><span className="stat__label">decisions</span></li>
            <li className={`stat stat--slipped${shown.slipped.length ? " stat--warn" : ""}`}><span className="stat__icon" aria-hidden="true"><FontAwesomeIcon icon={faFlag} /></span><span className="stat__value">{shown.slipped.length}</span><span className="stat__label">slipped</span></li>
            <li className="stat stat--talk"><span className="stat__icon" aria-hidden="true"><FontAwesomeIcon icon={faComments} /></span><span className="stat__value">{messages}</span><span className="stat__label">messages</span></li>
            <li className="stat stat--wide"><ProgressRing done={shown.progress.done} total={shown.progress.total} /></li>
          </ul>

          <div className="reflection__charts">
            {shown.days && shown.days.length === 7 && (
              <section className="panel-card reflect" aria-labelledby="r-days">
                <h3 id="r-days">Day by day</h3>
                <WeekByDay days={shown.days} today={today} />
              </section>
            )}
            <section className="panel-card reflect" aria-labelledby="r-plan">
              <h3 id="r-plan">The plan right now</h3>
              <PlanStatus tasks={(state?.tasks ?? []).filter((t) => t.task_id)} />
            </section>
          </div>

          <div className="reflection__grid">
            <section className="panel-card reflect" aria-labelledby="r-topics">
              <h3 id="r-topics">What you talked about</h3>
              {shown.topics.length ? (
                <Capped className="topics" limit={2} title="What you talked about" items={shown.topics}
                  render={(t) => <li key={t.title}><strong>{t.title}</strong><p className="muted topics__summary">{t.summary}</p></li>} />
              ) : (
                <p className="muted small">Not enough chat this week for Cadence to sum up.</p>
              )}
              {shown.topics.length > 0 && <p className="reflect__by small">Summed up by Cadence from the week's chat.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-done">
              <h3 id="r-done">Done this week</h3>
              {shown.done.length ? <Capped className="reflect__list" limit={4} title="Done this week" items={shown.done} render={(t) => <TaskLine key={t.task_id} task={t} today={today} nameOf={nameOf} withDate={false} />} /> : <p className="muted small">Nothing finished this week.</p>}
              {shown.added.length > 0 && (
                <>
                  <h4>New tasks · {gaps > 0 ? `${gaps} of ${shown.added.length} still need an owner or a date` : "all with an owner and a date"}</h4>
                  <Capped className="reflect__list" limit={4} title="New tasks this week" items={shown.added} render={(t) => <TaskLine key={t.task_id} task={t} today={today} nameOf={nameOf} />} />
                </>
              )}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-decided">
              <h3 id="r-decided">Decided</h3>
              {shown.decisions.length ? (
                <Capped className="reflect__list" limit={4} title="Decided this week" items={shown.decisions}
                  render={(d) => <li key={d.decision_id}><strong>{d.choice}</strong> <span className="muted">· {d.question}</span></li>} />
              ) : <p className="muted small">No decision this week.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-slipped">
              <h3 id="r-slipped">What slipped</h3>
              {shown.slipped.length ? (
                <Capped className="reflect__list" limit={4} title="What slipped" items={shown.slipped} render={(t) => <li key={t.task_id}>{t.title} <span className="due due--late">{t.due_date ? dayLabel(t.due_date) : ""}</span></li>} />
              ) : <p className="muted small">Nothing slipped.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-next">
              <h3 id="r-next">Coming up</h3>
              {shown.upcoming.length ? (
                <Capped className="reflect__list" limit={4} title="Coming up" items={shown.upcoming} render={(m) => <li key={m.milestone_id}>{m.title} <span className="due">{dayLabel(m.due_date)}</span></li>} />
              ) : <p className="muted small">No milestone in the next two weeks.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-where">
              <h3 id="r-where">Where you talked</h3>
              <ChannelBars talk={shown.talk} names={CHANNELS} />
            </section>
          </div>
        </>
      )}
    </section>
  );
}
