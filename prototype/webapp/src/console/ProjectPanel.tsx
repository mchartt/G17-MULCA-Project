import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBullseye, faFileLines, faFlag, faListCheck, faRotate, faScaleBalanced } from "../lib/icons";
import { useState, type FormEvent } from "react";
import type { Person, ProjectState } from "../lib/types";
import { formatDate } from "./ProposalCard";
import { dotFor } from "./space";

type Props = {
  state: ProjectState | null;
  members: Person[];
  onKickoff: () => void;
  onRefresh: () => void;
  /** M4: a member updates a task's status (their own action, no card). */
  onTaskStatus?: (taskId: string, status: string) => void;
  /** M4: "why did we decide X?"; resolves to the answer with its source. */
  onWhy?: (question: string) => Promise<string>;
};

const STATUSES = ["todo", "doing", "done", "blocked"];

/** The plan as the group agreed it: always visible next to the chat (UC9). */
export function ProjectPanel({ state, members, onKickoff, onRefresh, onTaskStatus, onWhy }: Props) {
  const charter = state?.charter;
  const nameOf = (id?: number | null) => members.find((m) => m.id === id)?.name;

  return (
    <aside className="panel" aria-labelledby="panel-title">
      <div className="panel__head">
        <h2 id="panel-title">Project plan</h2>
        <button className="btn btn--soft btn--small" onClick={onRefresh}><FontAwesomeIcon icon={faRotate} /> Refresh</button>
      </div>

      {/* The goal waits for the kickoff; tasks and decisions can come before it (M3 cards). */}
      {!charter ? (
        <div className="panel__empty">
          <p>No goal yet. Paste the assignment and Cadence proposes a goal, deliverables and milestones for the group to confirm.</p>
          <button className="btn btn--primary" onClick={onKickoff}><FontAwesomeIcon icon={faFileLines} /> Paste the assignment</button>
        </div>
      ) : (
        <section className="panel__section panel-card">
          <h3><FontAwesomeIcon icon={faBullseye} /> Goal</h3>
          <p className="panel__goal">{charter.goal}</p>
          {charter.confirmed_by && <p className="muted small">Confirmed by {nameOf(charter.confirmed_by) ?? "a member"}</p>}
        </section>
      )}
      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faFlag} /> Milestones</h3>
        {state?.milestones?.length ? (
          <ol className="timeline">
            {state.milestones.map((m) => (
              <li key={m.title}>
                <span className="timeline__date">{m.due_date ? formatDate(m.due_date) : "no date"}</span>
                <span>{m.title}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No milestones yet.</p>
        )}
      </section>

      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faListCheck} /> Tasks</h3>
        {state?.tasks?.length ? (
          <ul className="tasks">
            {state.tasks.map((t) => (
              <li key={t.title}>
                <span className="dot" style={{ background: t.owner_id ? dotFor(t.owner_id, members) : "var(--line)" }} aria-hidden="true" />
                <span className="tasks__title">{t.title}</span>
                <span className="muted small">{t.owner_id ? nameOf(t.owner_id) ?? "member" : "No owner"}</span>
                {onTaskStatus && t.task_id ? (
                  <select
                    className="tasks__status"
                    aria-label={`Status of ${t.title}`}
                    value={t.status}
                    onChange={(e) => onTaskStatus(t.task_id!, e.target.value)}
                  >
                    {STATUSES.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                ) : (
                  <span className="tag">{t.status}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No tasks yet. They arrive when a member takes a card or the group plans together.</p>
        )}
      </section>

      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faScaleBalanced} /> Decisions</h3>
        {state?.decisions?.length ? (
          <ul className="decisions">
            {state.decisions.map((d) => (
              <li key={d.question}>
                <p>{d.question}</p>
                <p className="decisions__choice">{d.choice}</p>
                {d.reason && <p className="muted small">{d.reason}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No decisions recorded yet.</p>
        )}
        {onWhy && !!state?.decisions?.length && <AskWhy onWhy={onWhy} />}
      </section>
    </aside>
  );
}

/** UC9: ask about a past decision; the answer cites the decision log. */
function AskWhy({ onWhy }: { onWhy: (q: string) => Promise<string> }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setAnswer(await onWhy(question.trim()));
    setBusy(false);
  }

  return (
    <form className="askwhy" onSubmit={submit}>
      <label htmlFor="askwhy-q" className="small">Ask why the group decided something</label>
      <div className="askwhy__row">
        <input id="askwhy-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Why did we choose…?" />
        <button className="btn btn--soft btn--small" type="submit" disabled={busy || !question.trim()}>{busy ? "Looking…" : "Ask"}</button>
      </div>
      {answer && <p className="askwhy__answer" role="status">{answer}</p>}
    </form>
  );
}
