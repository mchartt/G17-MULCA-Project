// The pages beside the chat (left rail): milestones, what waits on what, and
// how the plan stands. They are for looking; every creation opens a popup.
// Numbers and lists come from the saved plan only, and say nothing about people.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faFlag, faPlus, faTrashCan } from "../lib/icons";
import type { Milestone, ProjectState } from "../lib/types";
import { DependencyGraph } from "./DependencyGraph";
import { milestoneGroups, planFacts, waitingOn, type MilestoneEdit, type Task } from "./plan";

/** The milestones in three groups: to complete (a date ahead), date passed, date still to set. */
export function MilestonesPage({ milestones, today, onMilestone, onNew }: { milestones: Milestone[]; today: string; onMilestone: (edit: MilestoneEdit) => Promise<string | null>; onNew: () => void }) {
  const groups = milestoneGroups(milestones, today);
  const sections = [
    { key: "complete", title: "To complete", about: "A date still ahead.", items: groups.toComplete },
    { key: "schedule", title: "To schedule", about: "No date yet. Pick one and it moves up.", items: groups.toSchedule },
    { key: "passed", title: "Date passed", about: "The date is behind us. Move it, or remove it if it is done.", items: groups.passed },
  ].filter((s) => s.items.length > 0);

  return (
    <section className="page" aria-label="Milestones">
      <header className="page__head">
        <p className="muted">The dates the group works towards. Cadence reads them at the check-in.</p>
        <button className="btn btn--primary btn--small" onClick={onNew}><FontAwesomeIcon icon={faPlus} /> New milestone</button>
      </header>
      {sections.length === 0 ? (
        <p className="muted register__empty">No milestones yet. Add the first one with “New milestone”, or paste the assignment and Cadence proposes them.</p>
      ) : (
        sections.map((s) => (
          <section key={s.key} className="page__section" aria-labelledby={`ms-${s.key}`}>
            <h3 id={`ms-${s.key}`}>{s.title} <span className="muted small">{s.items.length}</span></h3>
            <p className="muted small">{s.about}</p>
            <ul className="register">
              {s.items.map((m) => (
                <li key={m.milestone_id ?? m.title} className="register__row">
                  <span className="register__flag" aria-hidden="true"><FontAwesomeIcon icon={faFlag} /></span>
                  <span className="register__title">{m.title}</span>
                  {m.milestone_id && (
                    <>
                      <input type="date" aria-label={`Date of ${m.title}`} value={m.due_date ?? ""} onChange={(e) => void onMilestone({ milestone: m.milestone_id!, due: e.target.value || null })} />
                      <button type="button" className="icon-btn" aria-label={`Remove ${m.title}`} onClick={() => void onMilestone({ milestone: m.milestone_id!, remove: true })}><FontAwesomeIcon icon={faTrashCan} /></button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </section>
  );
}

/** What waits on what: drawn, then listed in words (the list is the text alternative), with who is ready to start. */
export function DependenciesPage({ tasks, onNew, onLink }: { tasks: Task[]; onNew: () => void; onLink: (taskId: string | null) => void }) {
  const rows = waitingOn(tasks);
  return (
    <section className="page" aria-label="Dependencies">
      <header className="page__head">
        <p className="muted">When one task needs another to finish first, it waits on it.</p>
        <div className="page__actions">
          {tasks.length > 1 && <button className="btn btn--soft btn--small" onClick={() => onLink(null)}>Link tasks</button>}
          <button className="btn btn--primary btn--small" onClick={onNew}><FontAwesomeIcon icon={faPlus} /> New task</button>
        </div>
      </header>
      {rows.length === 0 ? (
        <p className="muted register__empty">Nothing waits on anything yet. In “New task”, choose what it waits on, or use “Link tasks” for tasks you already have.</p>
      ) : (
        <>
          <DependencyGraph tasks={tasks} />
          <section className="page__section" aria-labelledby="deps-list">
            <h3 id="deps-list">As a list</h3>
            <ul className="deps">
              {rows.map((row) => (
                <li key={row.task.task_id ?? row.task.title} className="deps__row">
                  <p>
                    <strong>{row.task.title}</strong>{" "}
                    <span className={row.waiting ? "tag tag--warn" : "tag"}>{row.task.status === "done" ? "Done" : row.waiting ? "Waiting" : "Ready to start"}</span>
                    {row.task.task_id && <button className="link-btn" aria-label={`Change what ${row.task.title} waits on`} onClick={() => onLink(row.task.task_id!)}>Change</button>}
                  </p>
                  <ul className="deps__needs" aria-label={`${row.task.title} waits on`}>
                    {row.needs.map((n) => (
                      <li key={n.task.task_id ?? n.task.title}>
                        {n.done ? <FontAwesomeIcon icon={faCheck} aria-hidden="true" /> : <span className="deps__open" aria-hidden="true" />}
                        {n.task.title} <span className="muted small">{n.done ? "done" : n.task.status}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}

/** How the plan stands today: a few counts and the decisions with their reasons. */
export function ReflectionPage({ state, today }: { state: ProjectState | null; today: string }) {
  const tasks = (state?.tasks ?? []) as Task[];
  const facts = planFacts(tasks, state?.milestones ?? [], today);
  const decisions = state?.decisions ?? [];
  const lines: [number, string][] = [
    [facts.late, "tasks are late"],
    [facts.noOwner, "open tasks have no owner"],
    [facts.noDate, "open tasks have no date"],
    [facts.milestonesPassed, "milestone dates have passed"],
    [facts.milestonesToSchedule, "milestones have no date yet"],
  ];
  return (
    <section className="page" aria-label="Reflection">
      <header className="page__head">
        <p className="muted">How the plan stands today. Counts from the saved plan, nothing about people.</p>
      </header>
      <section className="page__section" aria-labelledby="refl-plan">
        <h3 id="refl-plan">Planned and done</h3>
        {facts.tasks === 0 ? (
          <p className="muted register__empty">No tasks yet.</p>
        ) : (
          <>
            <progress className="refl__bar" max={facts.tasks} value={facts.done} aria-label="Tasks done" />
            <p><strong>{facts.done}</strong> of {facts.tasks} tasks done</p>
            <ul className="refl__facts">
              {lines.filter(([count]) => count > 0).map(([count, text]) => <li key={text}><strong>{count}</strong> {text}</li>)}
            </ul>
          </>
        )}
      </section>
      <section className="page__section" aria-labelledby="refl-decisions">
        <h3 id="refl-decisions">Decisions and why</h3>
        {decisions.length === 0 ? (
          <p className="muted register__empty">No decision recorded yet. When the group closes one on a card, it is kept here with its reason.</p>
        ) : (
          <ul className="refl__decisions">
            {decisions.map((d, i) => (
              <li key={`${i}-${d.question}`}>
                <p className="refl__q">{d.question}</p>
                <p><strong>{d.choice}</strong>{d.reason ? <span className="muted"> · {d.reason}</span> : null}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
