import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCalendarDays, faCircleQuestion, faFlag, faListCheck, faUserPen } from "../lib/icons";
import { todayIso, todayView, type Task } from "./plan";

type Props = {
  tasks: Task[];
  onTask: () => void;
  onMilestone: () => void;
  onToday: () => void;
  onProfile: () => void;
  onTour: () => void;
};

/** "Today: 2 due, 1 late": the same words the popup uses, so the button says what it opens. */
export function todayLabel(tasks: Task[]): { label: string; count: number } {
  const view = todayView(tasks, todayIso());
  const count = view.late.length + view.today.length;
  if (count === 0) return { label: "Today: nothing due", count };
  return { label: `Today: ${[view.today.length > 0 && `${view.today.length} due`, view.late.length > 0 && `${view.late.length} late`].filter(Boolean).join(", ")}`, count };
}

/**
 * The quick actions, always in the same place on the right: what a member
 * creates by hand (a task, a milestone), what is due today, their profile,
 * and the tour again. One small column, so the chat keeps the room.
 */
export function QuickRail({ tasks, onTask, onMilestone, onToday, onProfile, onTour }: Props) {
  const today = todayLabel(tasks);
  return (
    <nav className="rail" aria-label="Quick actions" data-tour="rail">
      <button className="rail__btn" aria-label="Create a task" onClick={onTask}><FontAwesomeIcon icon={faListCheck} /><span>Task</span></button>
      <button className="rail__btn" aria-label="Create a milestone" onClick={onMilestone}><FontAwesomeIcon icon={faFlag} /><span>Milestone</span></button>
      {/* Seen: "Today" and a badge; heard: the whole line ("Today: 1 late"). */}
      <button className="rail__btn" onClick={onToday}>
        <FontAwesomeIcon icon={faCalendarDays} />
        <span aria-hidden="true">Today</span>
        <span className="sr-only">{today.label}</span>
        {today.count > 0 && <b className="rail__badge" aria-hidden="true">{today.count}</b>}
      </button>
      <button className="rail__btn" aria-label="Your profile" onClick={onProfile}><FontAwesomeIcon icon={faUserPen} /><span>Profile</span></button>
      <button className="rail__btn rail__btn--quiet" aria-label="Show the tour again" onClick={onTour}><FontAwesomeIcon icon={faCircleQuestion} /><span>Tour</span></button>
    </nav>
  );
}
