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

/** "Ask why": a question about a past decision, answered from the decision log with its source. */
export function AskWhyDialog({ open, onClose, onWhy }: { open: boolean; onClose: () => void; onWhy: (question: string) => Promise<string> }) {
  const id = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) return;
    setQuestion("");
    setAnswer(null);
    setBusy(false);
  }, [open]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setAnswer(await onWhy(question.trim()));
    setBusy(false);
  }

  return (
    <Dialog open={open} title="Ask why" onClose={onClose}>
      <p className="muted">Ask why the group decided something. Cadence answers from the decision log and shows its source.</p>
      <form className="form" onSubmit={submit}>
        <label htmlFor={`${id}-q`}>Your question</label>
        <input id={`${id}-q`} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Why did we choose…?" maxLength={500} />
        {answer && <p className="askwhy__answer" role="status">{answer}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Close</button>
          <button type="submit" className="btn btn--primary" disabled={busy || !question.trim()}>{busy ? "Looking…" : "Ask"}</button>
        </div>
      </form>
    </Dialog>
  );
}

/** N3: milestones and task dates in each member's own calendar, read-only, through a private link. */
export function CalendarDialog({ open, onClose, onCalendar }: { open: boolean; onClose: () => void; onCalendar: () => Promise<string> }) {
  const id = useId();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) return;
    setError(null);
    setCopied(false);
  }, [open]);

  async function make() {
    setError(null);
    setCopied(false);
    try {
      setUrl(await onCalendar());
    } catch (e) {
      setError(e instanceof Error ? e.message : "The link could not be created.");
    }
  }

  return (
    <Dialog open={open} title="Add to my calendar" onClose={onClose}>
      <p className="muted">Milestones and task dates appear in your own calendar, read-only. Keep the link private: a new link turns the old one off.</p>
      <div className="calendar">
        <div>
          <button type="button" className="btn btn--primary btn--small" onClick={() => void make()}>{url ? "Make a new link" : "Create my link"}</button>
        </div>
        {url && (
          <>
            <label htmlFor={`${id}-url`} className="small">Subscribe to this link. Google Calendar: Other calendars, From URL. Outlook: Add calendar, Subscribe from web.</label>
            <div className="askwhy__row">
              <input id={`${id}-url`} readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
              <button type="button" className="btn btn--soft btn--small" onClick={() => void navigator.clipboard?.writeText(url).then(() => setCopied(true))}>{copied ? "Copied" : "Copy"}</button>
            </div>
          </>
        )}
        {error && <p className="form__error" role="alert">{error}</p>}
      </div>
      <div className="form__actions"><button type="button" className="btn btn--soft" onClick={onClose}>Close</button></div>
    </Dialog>
  );
}

/**
 * Link tasks: choose a task and what it waits on. Opened from a row of the
 * dependency page (the task is already chosen) or from "Link tasks".
 * What it waits on is always saved as a whole list; the server refuses a
 * loop and says why.
 */
export function WaitsOnDialog({ open, tasks, taskId, onClose, onSave }: { open: boolean; tasks: Task[]; taskId: string | null; onClose: () => void; onSave: (taskId: string, waitsOn: string[]) => Promise<string | null> }) {
  const id = useId();
  const [chosen, setChosen] = useState("");
  const [waits, setWaits] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const current = (taskKey: string) => new Set(tasks.find((t) => t.task_id === taskKey)?.depends_on ?? []);

  // Every time it opens: the task asked for (or none), with what it waits on today.
  useEffect(() => {
    if (!open) return;
    setChosen(taskId ?? "");
    setWaits(taskId ? current(taskId) : new Set());
    setError(null);
    setBusy(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, taskId]);

  const open_tasks = tasks.filter((t) => t.task_id && t.status !== "done");
  // Offered: the other open tasks, and any task it already waits on (even done), so saving never drops one silently.
  const offered = tasks.filter((t) => t.task_id && t.task_id !== chosen && (t.status !== "done" || waits.has(t.task_id)));

  function pick(taskKey: string) {
    setChosen(taskKey);
    setWaits(current(taskKey));
    setError(null);
  }

  function toggle(taskKey: string) {
    const next = new Set(waits);
    if (!next.delete(taskKey)) next.add(taskKey);
    setWaits(next);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!chosen || busy) return;
    setBusy(true);
    const result = await onSave(chosen, offered.filter((t) => waits.has(t.task_id!)).map((t) => t.task_id!));
    setBusy(false);
    setError(result);
  }

  return (
    <Dialog open={open} title="Link tasks" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p className="muted small">A task that waits on another cannot start until the other is done.</p>
        <label htmlFor={`${id}-task`}>Task</label>
        <select id={`${id}-task`} className="field-select" value={chosen} onChange={(e) => pick(e.target.value)}>
          <option value="">Choose a task…</option>
          {open_tasks.map((t) => <option key={t.task_id} value={t.task_id}>{t.title}</option>)}
        </select>
        <fieldset className="form__waits" disabled={!chosen}>
          <legend>Waits on</legend>
          {offered.length === 0 ? (
            <p className="muted small">No other open task.</p>
          ) : (
            offered.map((t) => (
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
          <button type="submit" className="btn btn--primary" disabled={!chosen || busy}>Save</button>
        </div>
      </form>
    </Dialog>
  );
}
