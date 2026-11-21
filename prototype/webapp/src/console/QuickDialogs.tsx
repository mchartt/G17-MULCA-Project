// The quick actions: every creation by hand happens in a popup, and "Today"
// is one look at what needs a member's eyes now. A member's own action: no
// card, no model. The server checks every value again.
import { useEffect, useId, useState, type FormEvent } from "react";
import type { MemberId, Person } from "../lib/types";
import { Dialog } from "./Dialogs";
import { OwnerSelect } from "./PlanDialogs";
import { dayLabel, type MilestoneEdit, type NewTask, type Task } from "./plan";

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

/**
 * Find owners (Matteo, 20/11): every open task that nobody owns, listed, and
 * one button that asks Cadence to propose who could take each, from the
 * members' profiles. Cadence answers with one card in the chat; nothing is
 * assigned until a member confirms it.
 */
export function OwnersDialog({ open, tasks, onClose, onFind }: { open: boolean; tasks: Task[]; onClose: () => void; onFind: () => Promise<string | null> }) {
  const ownerless = tasks.filter((t) => !t.owner_id && t.status !== "done");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) setError(null);
  }, [open]);
  const find = async () => {
    setBusy(true);
    setError(await onFind());
    setBusy(false);
  };
  return (
    <Dialog open={open} title="Find owners" onClose={onClose}>
      {ownerless.length === 0 ? (
        <p className="muted">Every open task already has an owner.</p>
      ) : (
        <>
          <p className="muted">
            {ownerless.length === 1 ? "This task has no owner yet." : `These ${ownerless.length} tasks have no owner yet.`} Cadence
            proposes who could take each, from your profiles; one of you confirms the card in the chat.
          </p>
          <ul className="owners-list" aria-label="Tasks with no owner">
            {ownerless.map((t) => (
              <li key={t.task_id ?? t.title}>
                <span className="owners-list__title">{t.title}</span>
                {t.due_date && <span className="muted small">due {dayLabel(t.due_date)}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <p className="form__error" role="alert">{error}</p>}
      <div className="form__actions">
        <button type="button" className="btn btn--soft" onClick={onClose}>{ownerless.length > 0 ? "Cancel" : "Close"}</button>
        {ownerless.length > 0 && (
          <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void find()}>
            {busy ? "Asking Cadence…" : "Ask Cadence to propose owners"}
          </button>
        )}
      </div>
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
  const [find, setFind] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const current = (taskKey: string) => new Set(tasks.find((t) => t.task_id === taskKey)?.depends_on ?? []);

  // Every time it opens: the task asked for (or none), with what it waits on today.
  useEffect(() => {
    if (!open) return;
    setChosen(taskId ?? "");
    setWaits(taskId ? current(taskId) : new Set());
    setFind("");
    setError(null);
    setBusy(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, taskId]);

  const open_tasks = tasks.filter((t) => t.task_id && t.status !== "done");
  // Offered: the other open tasks, and any task it already waits on (even done), so saving never drops one silently.
  const offered = tasks.filter((t) => t.task_id && t.task_id !== chosen && (t.status !== "done" || waits.has(t.task_id)));
  const query = find.trim().toLowerCase();
  const listed = query ? offered.filter((t) => t.title.toLowerCase().includes(query)) : offered;
  const picked = offered.filter((t) => waits.has(t.task_id!));
  const title = tasks.find((t) => t.task_id === chosen)?.title ?? "";

  function pick(taskKey: string) {
    setChosen(taskKey);
    setWaits(current(taskKey));
    setFind("");
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
    const result = await onSave(chosen, picked.map((t) => t.task_id!));
    setBusy(false);
    setError(result);
  }

  return (
    <Dialog open={open} title="Link tasks" onClose={onClose}>
      <form className="form link" onSubmit={submit}>
        <label htmlFor={`${id}-task`}>Task</label>
        <select id={`${id}-task`} className="field-select" value={chosen} onChange={(e) => pick(e.target.value)}>
          <option value="">Choose a task…</option>
          {open_tasks.map((t) => <option key={t.task_id} value={t.task_id}>{t.title}</option>)}
        </select>
        {chosen && (
          <div className="link__now" aria-live="polite">
            <p className="small">
              {picked.length === 0 ? <>“{title}” can start now: it waits on nothing.</> : <>“{title}” starts only after:</>}
            </p>
            {picked.length > 0 && (
              <ul className="link__chips" aria-label="It waits on">
                {picked.map((t) => (
                  <li key={t.task_id}>
                    <span>{t.title}</span>
                    <button type="button" className="link__remove" aria-label={`Remove ${t.title}`} onClick={() => toggle(t.task_id!)}>×</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <fieldset className="form__waits link__pick" disabled={!chosen}>
          <legend>Waits on</legend>
          {offered.length > 5 && (
            <input className="link__find" type="search" placeholder="Find a task" aria-label="Find a task" value={find} onChange={(e) => setFind(e.target.value)} />
          )}
          {offered.length === 0 ? (
            <p className="muted small">No other open task.</p>
          ) : listed.length === 0 ? (
            <p className="muted small">No task matches “{find}”.</p>
          ) : (
            <div className="link__list">
              {listed.map((t) => (
                <label key={t.task_id} className="check">
                  <input type="checkbox" checked={waits.has(t.task_id!)} onChange={() => toggle(t.task_id!)} />
                  {t.title}
                </label>
              ))}
            </div>
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
