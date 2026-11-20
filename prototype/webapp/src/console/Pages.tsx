// The pages beside the chat (left rail): milestones, what waits on what, and
// how the plan stands. They are for looking; every creation opens a popup.
// Numbers and lists come from the saved plan only, and say nothing about people.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faFlag, faPlus, faTrashCan } from "../lib/icons";
import type { Milestone } from "../lib/types";
import { milestoneGroups, type MilestoneEdit } from "./plan";

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

// The other pages, redesigned 20/11, each in its own file.
export { DependenciesPage } from "./DependencyJam";
export { DecisionsPage } from "./DecisionsView";
export { ReflectionPage } from "./ReflectionView";
export { TasksPage } from "./TasksBoard";
