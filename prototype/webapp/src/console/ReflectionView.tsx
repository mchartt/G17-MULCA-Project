// Reflection (Matteo, 20/11): how the group worked in one week. The numbers
// and lists come from the plan and the chat (the server's "reflection"
// command); only "What you talked about" is written by Cadence, from the
// week's chat. Everything is about the group, never about one person: no
// per-member counts (the privacy promise: Cadence never scores or ranks people).
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useState } from "react";
import { faChevronLeft, faChevronRight } from "../lib/icons";
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

export function ReflectionPage({ today, onLoad }: Props) {
  const [week, setWeek] = useState(() => mondayOf(today));
  const [data, setData] = useState<Reflection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const current = week === mondayOf(today);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    void onLoad(week).then((answer) => {
      if (!alive) return;
      if (typeof answer === "string") setError(answer);
      else setData(answer);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [week, onLoad]);

  const shown = data && data.week === week ? data : null;
  const messages = shown?.talk.reduce((sum, t) => sum + t.messages, 0) ?? 0;
  const progress = shown && shown.progress.total ? Math.round((shown.progress.done / shown.progress.total) * 100) : 0;

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
            <li className="stat"><span className="stat__value">{shown.done.length}</span><span className="stat__label">tasks done</span></li>
            <li className="stat"><span className="stat__value">{shown.decisions.length}</span><span className="stat__label">decisions</span></li>
            <li className={`stat${shown.slipped.length ? " stat--warn" : ""}`}><span className="stat__value">{shown.slipped.length}</span><span className="stat__label">slipped</span></li>
            <li className="stat"><span className="stat__value">{messages}</span><span className="stat__label">messages</span></li>
            <li className="stat stat--wide">
              <span className="stat__value">{progress}%</span>
              <span className="stat__label">of the plan done ({shown.progress.done} of {shown.progress.total})</span>
              <span className="progress progress--wide" role="progressbar" aria-label="Plan progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><i style={{ width: `${progress}%` }} /></span>
            </li>
          </ul>

          <div className="reflection__grid">
            <section className="panel-card reflect" aria-labelledby="r-topics">
              <h3 id="r-topics">What you talked about</h3>
              {shown.topics.length ? (
                <ul className="topics">
                  {shown.topics.map((t) => (
                    <li key={t.title}><strong>{t.title}</strong><p className="muted">{t.summary}</p></li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">Not enough chat this week for Cadence to sum up.</p>
              )}
              {shown.topics.length > 0 && <p className="reflect__by small">Summed up by Cadence from the week's chat.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-done">
              <h3 id="r-done">Done this week</h3>
              {shown.done.length ? <ul className="reflect__list">{shown.done.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul> : <p className="muted small">Nothing finished this week.</p>}
              {shown.added.length > 0 && (
                <>
                  <h4>New tasks</h4>
                  <ul className="reflect__list">{shown.added.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul>
                </>
              )}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-decided">
              <h3 id="r-decided">Decided</h3>
              {shown.decisions.length ? (
                <ul className="reflect__list">
                  {shown.decisions.map((d) => <li key={d.decision_id}><strong>{d.choice}</strong> <span className="muted">· {d.question}</span></li>)}
                </ul>
              ) : <p className="muted small">No decision this week.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-slipped">
              <h3 id="r-slipped">What slipped</h3>
              {shown.slipped.length ? (
                <ul className="reflect__list">{shown.slipped.map((t) => <li key={t.task_id}>{t.title} <span className="due due--late">{t.due_date ? dayLabel(t.due_date) : ""}</span></li>)}</ul>
              ) : <p className="muted small">Nothing slipped.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-next">
              <h3 id="r-next">Coming up</h3>
              {shown.upcoming.length ? (
                <ul className="reflect__list">{shown.upcoming.map((m) => <li key={m.milestone_id}>{m.title} <span className="due">{dayLabel(m.due_date)}</span></li>)}</ul>
              ) : <p className="muted small">No milestone in the next two weeks.</p>}
            </section>

            <section className="panel-card reflect" aria-labelledby="r-where">
              <h3 id="r-where">Where you talked</h3>
              <ul className="reflect__list">
                {shown.talk.map((t) => <li key={t.channel}>{CHANNELS[t.channel] ?? t.channel} <span className="muted">{t.messages} message{t.messages === 1 ? "" : "s"}</span></li>)}
              </ul>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
