import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faFileLines, faListOl, faUserPen } from "../lib/icons";
import type { MemberId, ProjectState } from "../lib/types";

type Props = {
  state: ProjectState | null;
  me: MemberId | null;
  onProfile: () => void;
  onKickoff: () => void;
  onPlanning: () => void;
};

/** Which of the three first steps are done, read from the saved project state. */
export function firstSteps(state: ProjectState | null, me: MemberId | null): { profile: boolean; charter: boolean; plan: boolean } {
  const mine = state?.members?.find((m) => me !== null && String(m.member_id) === String(me));
  return {
    profile: !!mine && (!!mine.discipline?.trim() || (mine.skills?.length ?? 0) > 0),
    charter: !!state?.charter,
    plan: (state?.tasks?.length ?? 0) > 0,
  };
}

/**
 * How a new space starts, in order: your profile, the assignment, the tasks.
 * Shown above the chat until the three are done; the next step to do is the
 * highlighted one. Nothing here is saved: each button opens the same dialog
 * as the toolbar, and a step ticks off when the project state says so.
 */
export function FirstSteps({ state, me, onProfile, onKickoff, onPlanning }: Props) {
  if (!state) return null; // not loaded yet: do not flash the list
  const done = firstSteps(state, me);
  if (done.profile && done.charter && done.plan) return null;

  const steps = [
    {
      key: "profile",
      done: done.profile,
      title: "Fill in your profile",
      about: "Your discipline, skills and weekly hours. Cadence uses them to suggest who could take each task.",
      button: "Add my profile",
      icon: faUserPen,
      run: onProfile,
    },
    {
      key: "charter",
      done: done.charter,
      title: "Paste the assignment",
      about: "Cadence proposes the goal, deliverables and milestones. They are saved when a member confirms the card.",
      button: "Add the assignment",
      icon: faFileLines,
      run: onKickoff,
    },
    {
      key: "plan",
      done: done.plan,
      title: "List your tasks",
      about: "Write the tasks you agreed on. Cadence suggests an owner for each; a member confirms the plan.",
      button: "Add the tasks",
      icon: faListOl,
      run: onPlanning,
    },
  ];
  const next = steps.find((s) => !s.done)?.key;

  return (
    <section className="steps" aria-labelledby="steps-title">
      <h3 id="steps-title">Getting started</h3>
      <ol>
        {steps.map((s, n) => (
          <li key={s.key} className={`steps__step${s.done ? " steps__step--done" : ""}${s.key === next ? " steps__step--next" : ""}`} aria-current={s.key === next ? "step" : undefined}>
            <span className="steps__mark" aria-hidden="true">{s.done ? <FontAwesomeIcon icon={faCheck} /> : n + 1}</span>
            <div>
              <p className="steps__title">
                {s.title}
                {s.done && <span className="sr-only"> (done)</span>}
              </p>
              {!s.done && <p className="muted small">{s.about}</p>}
            </div>
            {!s.done && (
              <button className={`btn btn--small ${s.key === next ? "btn--primary" : "btn--soft"}`} onClick={s.run}>
                <FontAwesomeIcon icon={s.icon} /> {s.button}
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
