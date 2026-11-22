import { useId, useState } from "react";
import type { CatchUp, CatchUpChannel, MemberId } from "../lib/types";
import { Capped } from "./Capped";
import { Dialog } from "./Dialogs";

const CHANNEL_NAMES: Record<string, string> = { web: "the web space", discord: "Discord", slack: "Slack" };
const time = (unix: number) => new Date(unix * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
const day = (unix: number) => new Date(unix * 1000).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

type Props = {
  open: boolean;
  summary: string;
  catchup: CatchUp | null;
  inviteCode: string;
  nameOf: (id?: MemberId | null) => string | undefined;
  /** Load the catch-up again from a day (YYYY-MM-DD), or from the last visit (null). */
  onSince: (day: string | null) => void;
  onClose: () => void;
};

/** The raw messages of one place, closed by default: the recap above is what to read first. */
function Messages({ place, title }: { place: CatchUpChannel; title: string }) {
  return (
    <details className="catchup__place">
      <summary>
        {title} <span className="muted small">{place.total} message{place.total === 1 ? "" : "s"}</span>
      </summary>
      {place.total > place.messages.length && <p className="muted small">The last {place.messages.length} are shown.</p>}
      <ul className="catchup__messages">
        {place.messages.map((m, i) => (
          <li key={i}>
            <span className="muted small">{time(m.at)}</span> <strong>{m.speaker === "coordinator" ? "Cadence" : m.speaker}</strong>: {m.text}
          </li>
        ))}
      </ul>
    </details>
  );
}

/**
 * "What did I miss?" (CS12), since the member's last visit or a day they
 * choose. First a short recap (the topics, summed up by Cadence from those
 * messages only, and labelled so), then the facts: decisions from the log,
 * tasks done and added from the plan, and the messages themselves.
 */
export function CatchUpDialog({ open, summary, catchup, inviteCode, nameOf, onSince, onClose }: Props) {
  const id = useId();
  const [from, setFrom] = useState<string>("");

  const loading = !summary;
  // The recap (new servers), or the topics alone (older ones).
  const recap = catchup?.recap ?? { overview: "", topics: catchup?.topics ?? [], open: [] };
  const done = catchup?.tasks_done ?? [];
  const added = catchup?.tasks_added ?? [];
  const places = [
    ...(catchup?.here && catchup.here.messages.length ? [{ place: catchup.here, title: "In this chat" }] : []),
    ...(catchup?.elsewhere ?? []).filter((p) => p.messages.length > 0).map((p) => ({ place: p, title: `On ${CHANNEL_NAMES[p.channel] ?? p.channel}` })),
  ];
  const said = places.reduce((sum, p) => sum + p.place.total, 0);
  const owner = (ownerId?: MemberId | null) => (ownerId ? <span className="muted"> · {nameOf(ownerId) ?? "a member"}</span> : null);

  return (
    <Dialog open={open} title="Catch up" onClose={onClose}>
      <div className="catchup" aria-busy={loading}>
        <div className="catchup__from" role="group" aria-labelledby={`${id}-from`}>
          <span id={`${id}-from`} className="small">From</span>
          <button type="button" className="chip" aria-pressed={!from} onClick={() => { setFrom(""); onSince(null); }}>
            Your last visit
          </button>
          <label className="catchup__day">
            <span className="sr-only">A day of your choice</span>
            <input type="date" value={from} max={new Date().toISOString().slice(0, 10)} onChange={(e) => { setFrom(e.target.value); if (e.target.value) onSince(e.target.value); }} />
          </label>
        </div>
        {catchup?.since !== undefined && !loading && <p className="muted small">{catchup.first && !from ? `Your first catch-up: the last 7 days, since ${day(catchup.since)}.` : `Since ${day(catchup.since)}.`}</p>}

        <p role="status" className="catchup__line">{loading ? "Cadence is reading the chat and summing it up…" : summary}</p>

        {catchup && !catchup.linked && (
          <p className="muted small">
            To link a channel, write <code>/coordinator link {inviteCode}</code> in your group's Discord or Slack channel.
          </p>
        )}

        {catchup && (
          <section className="catchup__brief" aria-labelledby={`${id}-brief`}>
            <h3 id={`${id}-brief`}>In brief</h3>
            {recap.overview && <p className="catchup__overview">{recap.overview}</p>}
            {recap.topics.length > 0 && (
              <ul>{recap.topics.map((t) => <li key={t.title}><strong>{t.title}</strong>: {t.summary}</li>)}</ul>
            )}
            {recap.open.length > 0 && (
              <>
                <h4>Still open</h4>
                <ul>{recap.open.map((q) => <li key={q}>{q}</li>)}</ul>
              </>
            )}
            {said === 0 ? (
              <p className="muted small">Nobody wrote in the chat since then.</p>
            ) : !recap.overview && recap.topics.length === 0 ? (
              <p className="muted small">Nothing to sum up in these {said} message{said === 1 ? "" : "s"}: they are below.</p>
            ) : (
              <p className="catchup__by small">Summed up by Cadence from these messages only. The facts below come from the plan and the decision log.</p>
            )}
          </section>
        )}

        {catchup && catchup.decisions.length > 0 && (
          <section aria-labelledby={`${id}-decisions`}>
            <h3 id={`${id}-decisions`}>Decided <span className="count">{catchup.decisions.length}</span></h3>
            <Capped className="catchup__facts" limit={3} title="Decided" items={catchup.decisions} render={(d) => (
              <li key={`${d.question}-${d.decided_at}`}>
                <strong>{d.choice}</strong> <span className="muted">· {d.question}</span>
                {d.reason && <p className="muted small">{d.reason}</p>}
              </li>
            )} />
          </section>
        )}

        {(done.length > 0 || added.length > 0) && (
          <section aria-labelledby={`${id}-plan`}>
            <h3 id={`${id}-plan`}>In the plan</h3>
            <Capped className="catchup__facts" limit={4} title="In the plan" items={[...done.map((t) => ({ t, done: true })), ...added.map((t) => ({ t, done: false }))]} render={({ t, done: finished }) => (
              <li key={`${finished ? "d" : "a"}-${t.task_id}`}>
                <span className={`tag${finished ? " tag--on" : ""}`}>{finished ? "Done" : "New"}</span> {t.title}{owner(t.owner_id)}
              </li>
            )} />
          </section>
        )}

        {places.length > 0 && (
          <section aria-label="Messages">
            {places.map(({ place, title }) => <Messages key={title} place={place} title={title} />)}
          </section>
        )}

        <div className="form__actions">
          <button type="button" className="btn btn--primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </Dialog>
  );
}
