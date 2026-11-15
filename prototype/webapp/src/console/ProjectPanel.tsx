import type { Person, ProjectState } from "../lib/types";
import { formatDate } from "./ProposalCard";
import { dotFor } from "./space";

type Props = {
  state: ProjectState | null;
  members: Person[];
  onKickoff: () => void;
  onRefresh: () => void;
};

/** The plan as the group agreed it: always visible next to the chat (UC9). */
export function ProjectPanel({ state, members, onKickoff, onRefresh }: Props) {
  const charter = state?.charter;
  const nameOf = (id?: number | null) => members.find((m) => m.id === id)?.name;

  return (
    <aside className="panel" aria-labelledby="panel-title">
      <div className="panel__head">
        <h2 id="panel-title">Project plan</h2>
        <button className="btn btn--quiet btn--small" onClick={onRefresh}>Refresh</button>
      </div>

      {!charter ? (
        <div className="panel__empty">
          <p>No goal yet. Paste the assignment and Cadence proposes a goal, deliverables and milestones for the group to confirm.</p>
          <button className="btn btn--confirm" onClick={onKickoff}>Paste the assignment</button>
        </div>
      ) : (
        <>
          <section className="panel__section">
            <h3>Goal</h3>
            <p className="panel__goal">{charter.goal}</p>
            {charter.confirmed_by && <p className="muted small">Confirmed by {nameOf(charter.confirmed_by) ?? "a member"}</p>}
          </section>

          <section className="panel__section">
            <h3>Milestones</h3>
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

          <section className="panel__section">
            <h3>Tasks</h3>
            {state?.tasks?.length ? (
              <ul className="tasks">
                {state.tasks.map((t) => (
                  <li key={t.title}>
                    <span className="dot" style={{ background: t.owner_id ? dotFor(t.owner_id, members) : "var(--line)" }} aria-hidden="true" />
                    <span className="tasks__title">{t.title}</span>
                    <span className="muted small">{t.owner_id ? nameOf(t.owner_id) ?? "member" : "No owner"}</span>
                    <span className="tag">{t.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No tasks yet. They come with the planning step.</p>
            )}
          </section>

          <section className="panel__section">
            <h3>Decisions</h3>
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
          </section>
        </>
      )}
    </aside>
  );
}
