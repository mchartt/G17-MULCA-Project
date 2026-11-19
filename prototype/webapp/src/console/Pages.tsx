// The pages beside the chat (left rail): milestones, what waits on what, and
// how the plan stands. They are for looking; every creation opens a popup.
// Numbers and lists come from the saved plan only, and say nothing about people.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faFlag, faPlus, faTrashCan } from "../lib/icons";
import type { MemberId, Milestone, ProjectState } from "../lib/types";
import { DependencyGraph } from "./DependencyGraph";
import { DoneBox } from "./PlanDialogs";
import { dayLabel, milestoneGroups, planFacts, waitingOn, type MilestoneEdit, type Task, type TaskEdit } from "./plan";

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

/** The tasks in four groups, from what needs attention to what is done. Owners and dates as the plan has them. */
export function TasksPage({ tasks, today, me = null, nameOf, onTask, onNew }: { tasks: Task[]; today: string; me?: MemberId | null; nameOf: (id: MemberId) => string | undefined; onTask: (taskId: string, edit: TaskEdit) => void; onNew: () => void }) {
  const waits = new Set(waitingOn(tasks).filter((r) => r.waiting).map((r) => r.task));
  const titleOf = new Map(tasks.filter((t) => t.task_id).map((t) => [t.task_id!, t.title]));
  const sections = [
    { key: "stuck", title: "Blocked or waiting", about: "Marked blocked, or waiting on a task that is not done.", items: tasks.filter((t) => t.status !== "done" && (t.status === "blocked" || waits.has(t))) },
    { key: "doing", title: "In progress", about: "Someone is working on it.", items: tasks.filter((t) => t.status === "doing" && !waits.has(t)) },
    { key: "todo", title: "To do", about: "Not started yet.", items: tasks.filter((t) => (t.status === "todo" || !t.status) && !waits.has(t)) },
    { key: "done", title: "Done", about: "", items: tasks.filter((t) => t.status === "done") },
  ].filter((s) => s.items.length > 0);

  return (
    <section className="page" aria-label="Tasks">
      <header className="page__head">
        <p className="muted">Every task of the plan. Cadence suggests owners and dates in the chat; here you change them by hand.</p>
        <button className="btn btn--primary btn--small" onClick={onNew}><FontAwesomeIcon icon={faPlus} /> New task</button>
      </header>
      {sections.length === 0 ? (
        <p className="muted register__empty">No tasks yet. Say in the chat what needs doing (Cadence offers to note it), or add one with “New task”.</p>
      ) : (
        sections.map((s) => (
          <section key={s.key} className="page__section" aria-labelledby={`tasks-${s.key}`}>
            <h3 id={`tasks-${s.key}`}>{s.title} <span className="muted small">{s.items.length}</span></h3>
            {s.about && <p className="muted small">{s.about}</p>}
            <ul className="register">
              {s.items.map((t) => {
                const late = t.status !== "done" && t.due_date && t.due_date < today;
                return (
                  <li key={t.task_id ?? t.title} className="register__row task-row">
                    <DoneBox task={t} onTask={onTask} />
                    <span className="register__title">
                      {t.title}
                      {(t.depends_on ?? []).length > 0 && (
                        <span className="muted small task-row__waits"> waits on {(t.depends_on ?? []).map((id) => titleOf.get(id)).filter(Boolean).join(", ")}</span>
                      )}
                    </span>
                    <span className="task-row__owner">
                      {t.owner_id ? nameOf(t.owner_id) ?? "a member" : <span className="muted">No owner</span>}
                      {/* An unowned task is a gap (CS5): one click for the member who steps up. */}
                      {!t.owner_id && t.task_id && me !== null && t.status !== "done" && (
                        <button className="link-btn" aria-label={`Take ${t.title}`} onClick={() => onTask(t.task_id!, { owner: me })}>I'll take it</button>
                      )}
                    </span>
                    <span className={`task-row__due${late ? " task-row__due--late" : ""}`}>{t.due_date ? `${late ? "Late · " : ""}${dayLabel(t.due_date)}` : <span className="muted">No date</span>}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </section>
  );
}

/**
 * The plan and decision registry: the confirmed goal and deliverables, then
 * every decision with its reason. Only what a member confirmed is here;
 * changing it goes through the chat (Cadence proposes a card) or the plan panel.
 */
export function DecisionsPage({ state, nameOf, onPlan }: { state: ProjectState | null; nameOf: (id: MemberId) => string | undefined; onPlan: () => void }) {
  const charter = state?.charter;
  const decisions = state?.decisions ?? [];
  return (
    <section className="page" aria-label="Decisions">
      <header className="page__head">
        <p className="muted">What the group agreed, with the reasons. To change something, say it in the chat: Cadence proposes the change as a card.</p>
        <button className="btn btn--soft btn--small" onClick={onPlan}>Edit the plan</button>
      </header>
      <section className="page__section" aria-labelledby="dec-plan">
        <h3 id="dec-plan">The plan</h3>
        {charter ? (
          <div className="registry__plan">
            <p className="registry__goal">{charter.goal}</p>
            {(charter.deliverables ?? []).length > 0 && (
              <ul className="registry__deliverables">{charter.deliverables!.map((d) => <li key={d}>{d}</li>)}</ul>
            )}
            {charter.confirmed_by !== undefined && <p className="muted small">Confirmed by {nameOf(charter.confirmed_by) ?? "a member"}.</p>}
          </div>
        ) : (
          <p className="muted register__empty">No plan confirmed yet. Paste the brief (or describe the project in the chat) and Cadence proposes a goal and deliverables to confirm.</p>
        )}
      </section>
      <section className="page__section" aria-labelledby="dec-list">
        <h3 id="dec-list">Decisions <span className="muted small">{decisions.length}</span></h3>
        {decisions.length === 0 ? (
          <p className="muted register__empty">No decision recorded yet. When the group closes a choice on a card, it is kept here with who decided and why.</p>
        ) : (
          <ol className="registry__decisions">
            {[...decisions].reverse().map((d, i) => (
              <li key={`${i}-${d.question}`}>
                <p className="refl__q">{d.question}</p>
                <p><strong>{d.choice}</strong></p>
                {d.reason && <p className="muted">Why: {d.reason}</p>}
                {(d.decided_by !== undefined || d.decided_at) && (
                  <p className="muted small">
                    {d.decided_by !== undefined && <>Closed by {nameOf(d.decided_by) ?? "a member"}</>}
                    {d.decided_at ? <> · {new Date(d.decided_at > 1e12 ? d.decided_at : d.decided_at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</> : null}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}
