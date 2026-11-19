// The quick actions: every creation by hand happens in a popup, and "Today"
// is one look at what needs a member's eyes now. A member's own action: no
// card, no model. The server checks every value again.
import { useEffect, useId, useState, type FormEvent } from "react";
import type { MemberId, Person } from "../lib/types";
import { Dialog } from "./Dialogs";
import { DoneBox, OwnerSelect } from "./PlanDialogs";
import { dayLabel, todayView, type MilestoneEdit, type NewTask, type Task, type TaskEdit } from "./plan";

type Create<T> = (value: T) => Promise<string | null>;

/** New task: name, description, owner, date, and the open tasks it waits on. */
export function NewTaskDialog({ open, tasks, members, onClose, onCreate }: { open: boolean; tasks: Task[]; members: Person[]; onClose: () => void; onCreate: Create<NewTask> }) {
  const id = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState<MemberId | null>(null);
  const [due, setDue] = useState("");
  const [waits, setWaits] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // It starts empty every time it opens.
  useEffect(() => {
    if (open) return;
    setTitle("");
    setDescription("");
    setOwner(null);
    setDue("");
    setWaits(new Set());
    setError(null);
    setBusy(false);
  }, [open]);

  const candidates = tasks.filter((t) => t.status !== "done" && t.task_id);

  function toggle(taskId: string) {
    const next = new Set(waits);
    if (!next.delete(taskId)) next.add(taskId);
    setWaits(next);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    setError(null);
    const waitsOn = candidates.filter((t) => waits.has(t.task_id!)).map((t) => t.task_id!);
    const result = await onCreate({ title: title.trim(), description: description.trim(), owner, due: due || null, waitsOn });
    setBusy(false);
    setError(result);
  }

  return (
    <Dialog open={open} title="New task" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label htmlFor={`${id}-title`}>Name</label>
        <input id={`${id}-title`} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="What has to be done" autoFocus />
        <label htmlFor={`${id}-description`}>Description (optional)</label>
        <textarea id={`${id}-description`} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} placeholder="What done looks like, or what the others should know" />
        <div className="form__pair">
          <div>
            <label htmlFor={`${id}-owner`}>Owner</label>
            <OwnerSelect id={`${id}-owner`} label="Owner" value={owner} members={members} nobody="No owner yet" onChange={setOwner} />
          </div>
          <div>
            <label htmlFor={`${id}-due`}>Due date</label>
            <input id={`${id}-due`} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>
        <fieldset className="form__waits">
          <legend>Waits on (optional)</legend>
          {candidates.length === 0 ? (
            <p className="muted small">No other open task yet.</p>
          ) : (
            candidates.map((t) => (
              <label key={t.task_id} className="check">
                <input type="checkbox" checked={waits.has(t.task_id!)} onChange={() => toggle(t.task_id!)} />
                {t.title}
              </label>
            ))
          )}
        </fieldset>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={!title.trim() || busy}>Add task</button>
        </div>
      </form>
    </Dialog>
  );
}

/** New milestone: a name and, when the group knows it, a date. */
export function NewMilestoneDialog({ open, onClose, onCreate }: { open: boolean; onClose: () => void; onCreate: Create<MilestoneEdit> }) {
  const id = useId();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) return;
    setTitle("");
    setDue("");
    setError(null);
    setBusy(false);
  }, [open]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    const result = await onCreate({ add: title.trim(), due: due || null });
    setBusy(false);
    setError(result);
    if (!result) {
      setTitle("");
      setDue("");
    }
  }

  return (
    <Dialog open={open} title="New milestone" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p className="muted small">A date the group works towards. Cadence reads it at the check-in.</p>
        <label htmlFor={`${id}-title`}>Name</label>
        <input id={`${id}-title`} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="For example: prototype ready" autoFocus />
        <label htmlFor={`${id}-due`}>Date (optional)</label>
        <input id={`${id}-due`} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={!title.trim() || busy}>Add milestone</button>
        </div>
      </form>
    </Dialog>
  );
}

type TodayProps = {
  open: boolean;
  /** The day to look at, as YYYY-MM-DD (the caller's today). */
  today: string;
  tasks: Task[];
  nameOf: (id?: MemberId | null) => string | undefined;
  onTask: (taskId: string, edit: TaskEdit) => void;
  onClose: () => void;
};

/** What is late and what is due today: the quick look, not the whole plan. */
export function TodayDialog({ open, today, tasks, nameOf, onTask, onClose }: TodayProps) {
  const view = todayView(tasks, today);
  const groups = [
    { key: "late", title: "Late", tasks: view.late },
    { key: "today", title: "Due today", tasks: view.today },
  ].filter((g) => g.tasks.length > 0);
  return (
    <Dialog open={open} title="Today" onClose={onClose}>
      {groups.length === 0 ? (
        <p className="muted register__empty">Nothing is due today and nothing is late.</p>
      ) : (
        groups.map((g) => (
          <section key={g.key} aria-labelledby={`today-${g.key}`} className="agenda">
            <h3 id={`today-${g.key}`} className={g.key === "late" ? "agenda__day agenda__day--late" : "agenda__day"}>{g.title}</h3>
            <ul>
              {g.tasks.map((t) => (
                <li key={t.task_id ?? t.title} className="agenda__task">
                  <DoneBox task={t} onTask={onTask} />
                  <span>{t.title}{g.key === "late" && t.due_date && <span className="muted small"> · was due {dayLabel(t.due_date)}</span>}</span>
                  <span className={t.owner_id ? "muted small" : "tag tag--warn"}>{t.owner_id ? nameOf(t.owner_id) ?? "member" : "No owner"}</span>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      <div className="form__actions"><button type="button" className="btn btn--soft" onClick={onClose}>Close</button></div>
    </Dialog>
  );
}
