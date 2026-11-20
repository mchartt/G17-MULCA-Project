// The Tasks page (Matteo, 20/11): To do, Due soon, In progress, Completed,
// each row with its owner, progress, description and date; a row opens the
// task's details, where a member changes anything by hand (their own action:
// no card). Long titles are cut with an ellipsis and shown whole in the
// details, so text never overlaps.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useId, useState, type FormEvent } from "react";
import { faFlag, faLink, faPlus, faTrashCan } from "../lib/icons";
import type { MemberId, Person } from "../lib/types";
import { initials } from "./Chat";
import { Dialog } from "./Dialogs";
import { DoneBox, OwnerSelect } from "./PlanDialogs";
import { dayLabel, STATUSES, waitingOn, type Task, type TaskEdit } from "./plan";

type Tab = "todo" | "soon" | "doing" | "done";
const TAB_NAMES: Record<Tab, string> = { todo: "To do", soon: "Due soon", doing: "In progress", done: "Completed" };
const TAB_HELP: Record<Tab, string> = {
  todo: "Not started yet.",
  soon: "Open tasks that are late or due in the next 7 days, the soonest first.",
  doing: "Someone is on it.",
  done: "Finished, the most recent first.",
};
const STATUS_NAMES: Record<string, string> = { todo: "To do", doing: "In progress", done: "Done", blocked: "Blocked" };
const SOON_DAYS = 7;

const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
const byDue = (a: Task, b: Task) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999") || a.title.localeCompare(b.title);
const progressOf = (t: Task) => (t.status === "done" ? 100 : Math.max(0, Math.min(100, t.progress ?? 0)));

/** The tasks of each tab: a task can be both "Due soon" and "To do"/"In progress" (the same row, two views). */
export function taskTabs(tasks: Task[], today: string): Record<Tab, Task[]> {
  const open = tasks.filter((t) => t.status !== "done");
  const horizon = addDays(today, SOON_DAYS);
  return {
    todo: open.filter((t) => t.status === "todo" || t.status === "blocked").sort(byDue),
    soon: open.filter((t) => t.due_date && t.due_date <= horizon).sort(byDue),
    doing: open.filter((t) => t.status === "doing").sort(byDue),
    done: tasks.filter((t) => t.status === "done").sort((a, b) => (b.done_at ?? 0) - (a.done_at ?? 0)),
  };
}

type Props = {
  tasks: Task[];
  members: Person[];
  today: string;
  me: MemberId | null;
  nameOf: (id?: MemberId | null) => string | undefined;
  onTask: (taskId: string, edit: TaskEdit) => void;
  onNew: () => void;
  onLink: (taskId: string) => void;
};

export function TasksPage({ tasks, members, today, me, nameOf, onTask, onNew, onLink }: Props) {
  const tabs = taskTabs(tasks, today);
  const [tab, setTab] = useState<Tab>(() => (tabs.soon.length ? "soon" : "todo"));
  const [open, setOpen] = useState<string | null>(null);
  const titles = new Map(tasks.filter((t) => t.task_id).map((t) => [t.task_id!, t.title]));
  const waiting = new Set(waitingOn(tasks).filter((w) => w.waiting).map((w) => w.task.task_id));
  const shown = tabs[tab];
  const selected = tasks.find((t) => t.task_id === open) ?? null;

  return (
    <section className="page tasks-page" aria-label="Tasks">
      <header className="page__head">
        <div className="seg" role="tablist" aria-label="Tasks by state">
          {(Object.keys(TAB_NAMES) as Tab[]).map((key) => (
            <button
              key={key}
              role="tab"
              id={`tab-${key}`}
              aria-selected={tab === key}
              aria-controls="tasks-panel"
              className={`seg__item${key === "soon" && tabs.soon.some((t) => t.due_date! < today) ? " seg__item--alert" : ""}`}
              onClick={() => setTab(key)}
            >
              {TAB_NAMES[key]} <span className="seg__count">{tabs[key].length}</span>
            </button>
          ))}
        </div>
        <button className="btn btn--primary btn--small" onClick={onNew}><FontAwesomeIcon icon={faPlus} /> New task</button>
      </header>
      <div id="tasks-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="tasks-panel">
        <p className="muted small">{TAB_HELP[tab]}</p>
        {shown.length === 0 ? (
          <p className="tasks-empty">{tab === "done" ? "Nothing finished yet." : tab === "soon" ? "Nothing due in the next 7 days." : "Nothing here."}</p>
        ) : (
          <ul className="task-list">
            {shown.map((t) => {
              const late = t.status !== "done" && !!t.due_date && t.due_date < today;
              const owner = t.owner_id ? nameOf(t.owner_id) ?? "A member" : null;
              const progress = progressOf(t);
              return (
                <li key={t.task_id ?? t.title} className={`task-card${t.status === "done" ? " task-card--done" : ""}`}>
                  {t.task_id && <DoneBox task={t} onTask={onTask} />}
                  <button className="task-card__main" onClick={() => setOpen(t.task_id ?? null)} disabled={!t.task_id} aria-label={`${t.title}: open the details`}>
                    <span className="task-card__title" title={t.title}>{t.title}</span>
                    <span className="task-card__about">
                      {t.description ? t.description : <span className="muted">No description</span>}
                    </span>
                  </button>
                  <div className="task-card__meta">
                    {t.status === "blocked" && <span className="tag tag--warn"><FontAwesomeIcon icon={faFlag} /> Blocked</span>}
                    {t.task_id && waiting.has(t.task_id) && t.status !== "blocked" && (
                      <span className="tag" title={`Waits on ${(t.depends_on ?? []).map((id) => titles.get(id)).filter(Boolean).join(", ")}`}>
                        <FontAwesomeIcon icon={faLink} /> Waiting
                      </span>
                    )}
                    {owner ? (
                      <span className="task-card__owner" title={owner}><span className="avatar avatar--small task-card__avatar" aria-hidden="true">{initials(owner)}</span><span className="task-card__owner-name">{owner}</span></span>
                    ) : t.task_id && t.status !== "done" && me !== null ? (
                      <button className="btn btn--soft btn--small" aria-label={`I'll take it: ${t.title}`} onClick={() => onTask(t.task_id!, { owner: me })}>I'll take it</button>
                    ) : (
                      <span className="muted small">No owner</span>
                    )}
                    <span className="task-card__progress" title={`${progress}% done`}>
                      <span className="progress" role="progressbar" aria-label={`${t.title}: progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
                        <i style={{ width: `${progress}%` }} />
                      </span>
                      <span className="small">{progress}%</span>
                    </span>
                    <span className={`due${late ? " due--late" : ""}`}>{t.due_date ? `${late ? "Late · " : ""}${dayLabel(t.due_date)}` : "No date"}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <TaskSheet
        task={selected}
        tasks={tasks}
        members={members}
        titles={titles}
        onClose={() => setOpen(null)}
        onSave={(edit) => { if (selected?.task_id) onTask(selected.task_id, edit); setOpen(null); }}
        onLink={() => { if (selected?.task_id) { onLink(selected.task_id); setOpen(null); } }}
      />
    </section>
  );
}

/** The details of one task: everything a member can change by hand, saved together. */
function TaskSheet({ task, tasks, members, titles, onClose, onSave, onLink }: {
  task: Task | null;
  tasks: Task[];
  members: Person[];
  titles: Map<string, string>;
  onClose: () => void;
  onSave: (edit: TaskEdit) => void;
  onLink: () => void;
}) {
  const id = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("todo");
  const [owner, setOwner] = useState<MemberId | null>(null);
  const [due, setDue] = useState("");
  const [progress, setProgress] = useState(0);
  const [removing, setRemoving] = useState(false);
  useEffect(() => {
    if (!task) return;
    setTitle(task.title);
    setDescription(task.description ?? "");
    setStatus(task.status);
    setOwner(task.owner_id ?? null);
    setDue(task.due_date ?? "");
    setProgress(progressOf(task));
    setRemoving(false);
  }, [task]);

  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!task) return;
    const edit: TaskEdit = {};
    if (title.trim() && title.trim() !== task.title) edit.title = title.trim();
    if (description.trim() !== (task.description ?? "")) edit.description = description.trim();
    if (status !== task.status) edit.status = status;
    if ((owner ?? null) !== (task.owner_id ?? null)) edit.owner = owner;
    if ((due || null) !== (task.due_date ?? null)) edit.due = due || null;
    if (progress !== progressOf(task) && status !== "done") edit.progress = progress;
    if (Object.keys(edit).length) onSave(edit);
    else onClose();
  };
  const waits = (task?.depends_on ?? []).map((t) => titles.get(t)).filter(Boolean) as string[];
  const waitedBy = task?.task_id ? tasks.filter((t) => t.depends_on?.includes(task.task_id!)).map((t) => t.title) : [];

  return (
    <Dialog open={task !== null} title="Task details" onClose={onClose}>
      {task && (
        <form className="form task-sheet" onSubmit={save}>
          <label htmlFor={`${id}-title`}>Title</label>
          <input id={`${id}-title`} value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
          <label htmlFor={`${id}-about`}>Description</label>
          <textarea id={`${id}-about`} rows={3} maxLength={2000} value={description} placeholder="What it is, what done looks like." onChange={(e) => setDescription(e.target.value)} />
          <div className="task-sheet__row">
            <div>
              <label htmlFor={`${id}-status`}>Status</label>
              <select id={`${id}-status`} className="field-select" value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUSES.map((s) => <option key={s} value={s}>{STATUS_NAMES[s] ?? s}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor={`${id}-owner`}>Owner</label>
              <OwnerSelect id={`${id}-owner`} label="Owner" value={owner} members={members} nobody="No owner yet" onChange={setOwner} />
            </div>
            <div>
              <label htmlFor={`${id}-due`}>Due</label>
              <input id={`${id}-due`} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </div>
          </div>
          <label htmlFor={`${id}-progress`}>Progress <span className="muted">{status === "done" ? "100%" : `${progress}%`}</span></label>
          <input id={`${id}-progress`} type="range" min={0} max={100} step={10} value={status === "done" ? 100 : progress} disabled={status === "done"} onChange={(e) => setProgress(Number(e.target.value))} />
          <div className="task-sheet__links">
            <p className="small"><strong>Waits on:</strong> {waits.length ? waits.join(", ") : <span className="muted">nothing</span>}</p>
            {waitedBy.length > 0 && <p className="small"><strong>Needed by:</strong> {waitedBy.join(", ")}</p>}
            <button type="button" className="link-btn" onClick={onLink}>Change what it waits on</button>
          </div>
          <div className="form__actions task-sheet__actions">
            {removing ? (
              <>
                <span className="small">Remove “{task.title}” from the plan?</span>
                <button type="button" className="btn btn--soft" onClick={() => setRemoving(false)}>Keep it</button>
                <button type="button" className="btn btn--danger" onClick={() => onSave({ remove: true })}>Remove</button>
              </>
            ) : (
              <>
                <button type="button" className="btn btn--link btn--danger" onClick={() => setRemoving(true)}><FontAwesomeIcon icon={faTrashCan} /> Remove</button>
                <span className="task-sheet__spacer" />
                <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
                <button type="submit" className="btn btn--primary">Save</button>
              </>
            )}
          </div>
        </form>
      )}
    </Dialog>
  );
}
