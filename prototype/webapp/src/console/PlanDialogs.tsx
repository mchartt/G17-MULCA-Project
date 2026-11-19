// The plan's popups, opened from Quick access: planning as a list of tasks,
// the register of every task, and the plan day by day. Every change here is
// a member's own action.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { faCheck, faFlag, faTrashCan } from "../lib/icons";
import type { MemberId, Milestone, Person } from "../lib/types";
import { Dialog } from "./Dialogs";
import { agenda, dayLabel, STATUSES, todayIso, type NewTask, type Task, type TaskEdit } from "./plan";

/** "" in a select means nobody; a member's id travels as text and goes back as it was. */
function ownerFrom(value: string, members: Person[]): MemberId | null {
  return members.find((m) => String(m.id) === value)?.id ?? null;
}

export function OwnerSelect({ id, label, value, members, nobody, onChange }: { id?: string; label: string; value: MemberId | null | undefined; members: Person[]; nobody: string; onChange: (owner: MemberId | null) => void }) {
  return (
    <select id={id} className="field-select" aria-label={label} value={value === null || value === undefined ? "" : String(value)} onChange={(e) => onChange(ownerFrom(e.target.value, members))}>
      <option value="">{nobody}</option>
      {members.map((m) => <option key={m.id} value={String(m.id)}>{m.name}</option>)}
      {/* An owner from a linked channel (Discord, Slack) is not in this list: keep showing them. */}
      {value !== null && value !== undefined && !members.some((m) => String(m.id) === String(value)) && <option value={String(value)}>Member of a linked channel</option>}
    </select>
  );
}

type Row = { key: number; title: string; owner: MemberId | null; due: string };

/**
 * /planning as a list: one row per task, with an owner when the group
 * already knows who takes it. Rows without an owner are the ones Cadence
 * suggests for, reading the profiles. The result is one card to confirm.
 */
export function PlanningDialog({ open, members, onClose, onSend }: { open: boolean; members: Person[]; onClose: () => void; onSend: (items: NewTask[]) => Promise<string | null> }) {
  const blank = (key: number): Row => ({ key, title: "", owner: null, due: "" });
  const [rows, setRows] = useState<Row[]>([blank(0), blank(1), blank(2)]);
  const [next, setNext] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const filled = rows.filter((r) => r.title.trim());
  const open_ = filled.filter((r) => r.owner === null).length;

  const change = (key: number, patch: Partial<Row>) => setRows(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const add = () => {
    setRows([...rows, blank(next)]);
    setNext(next + 1);
  };

  /** Several lines pasted into one row become one row each. */
  function onPaste(e: ClipboardEvent<HTMLInputElement>, key: number) {
    const lines = e.clipboardData.getData("text").split(/[\n;]/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) return;
    e.preventDefault();
    const at = rows.findIndex((r) => r.key === key);
    const pasted = lines.map((title, n) => ({ ...blank(next + n), title }));
    setRows([...rows.slice(0, at), ...pasted, ...rows.slice(at + 1)].slice(0, 15));
    setNext(next + lines.length);
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>, key: number) {
    if (e.key === "Enter" && rows[rows.length - 1]?.key === key && rows.length < 15) {
      e.preventDefault();
      add();
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSend(filled.map((r) => ({ title: r.title.trim(), owner: r.owner, due: r.due || null })));
    setBusy(false);
    setError(result);
    if (!result) {
      setRows([blank(next), blank(next + 1), blank(next + 2)]);
      setNext(next + 3);
    }
  }

  return (
    <Dialog open={open} title="Plan the work together" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">One task per row. Pick an owner if the group already knows who takes it; leave "Cadence suggests" and Cadence proposes someone from the profiles, with a reason. Nothing is saved until a member confirms the card.</p>
        <ol className="rows">
          {rows.map((r, n) => (
            <li key={r.key}>
              <input aria-label={`Task ${n + 1}`} value={r.title} onChange={(e) => change(r.key, { title: e.target.value })} onPaste={(e) => onPaste(e, r.key)} onKeyDown={(e) => onKey(e, r.key)} maxLength={200} placeholder={n === 0 ? "Server API" : n === 1 ? "UI screens" : "User test with 5 people"} />
              <OwnerSelect label={`Owner of task ${n + 1}`} value={r.owner} members={members} nobody="Cadence suggests" onChange={(owner) => change(r.key, { owner })} />
              <input type="date" aria-label={`Date of task ${n + 1}`} value={r.due} min={todayIso()} onChange={(e) => change(r.key, { due: e.target.value })} />
              <button type="button" className="icon-btn" aria-label={`Remove task ${n + 1}`} disabled={rows.length === 1} onClick={() => setRows(rows.filter((x) => x.key !== r.key))}><FontAwesomeIcon icon={faTrashCan} /></button>
            </li>
          ))}
        </ol>
        <button type="button" className="link-btn" onClick={add} disabled={rows.length >= 15}>+ Add another task</button>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={busy || filled.length === 0}>
            {busy ? "Cadence is planning…" : open_ > 0 || filled.length === 0 ? "Suggest owners" : "Make the plan card"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

type Edits = { members: Person[]; nameOf: (id?: MemberId | null) => string | undefined; onTask: (taskId: string, edit: TaskEdit) => void };

const FILTERS = [
  { key: "open", label: "Open" },
  { key: "mine", label: "Mine" },
  { key: "nobody", label: "No owner" },
  { key: "done", label: "Done" },
  { key: "all", label: "All" },
] as const;

/**
 * Every task of the group in one place: who has it, when it is due, where it
 * stands. A member adds a task, gives it an owner or a date, closes it or
 * removes it here. The panel next to the chat shows only what comes next.
 */
export function TaskRegisterDialog({ open, tasks, me, onClose, onAdd, ...edits }: Edits & { open: boolean; tasks: Task[]; me: MemberId | null; onClose: () => void; onAdd: (task: NewTask) => Promise<string | null> }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("open");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState<MemberId | null>(null);
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const shown = tasks.filter((t) => {
    if (filter === "open") return t.status !== "done";
    if (filter === "done") return t.status === "done";
    if (filter === "mine") return me !== null && String(t.owner_id) === String(me);
    if (filter === "nobody") return !t.owner_id;
    return true;
  });

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    const result = await onAdd({ title: title.trim(), owner, due: due || null });
    setError(result);
    if (!result) {
      setTitle("");
      setDue("");
    }
  }

  return (
    <Dialog open={open} title="Edit tasks" onClose={onClose}>
      <form className="addrow" onSubmit={add}>
        <input aria-label="New task" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Add a task…" />
        <OwnerSelect label="Owner of the new task" value={owner} members={edits.members} nobody="No owner yet" onChange={setOwner} />
        <input type="date" aria-label="Date of the new task" value={due} onChange={(e) => setDue(e.target.value)} />
        <button className="btn btn--primary btn--small" type="submit" disabled={!title.trim()}>Add task</button>
      </form>
      {error && <p className="form__error" role="alert">{error}</p>}

      <div className="chips" role="group" aria-label="Show">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className="chip" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
        <span className="muted small">{shown.length} of {tasks.length}</span>
      </div>

      {shown.length === 0 ? (
        <p className="muted register__empty">{tasks.length === 0 ? "No tasks yet. Add one above, or plan the work together from the toolbar." : "No task matches this view."}</p>
      ) : (
        <ul className="register">
          {shown.map((t) => (
            <li key={t.task_id ?? t.title} className={t.status === "done" ? "register__row register__row--done" : "register__row"}>
              <DoneBox task={t} onTask={edits.onTask} />
              <span className="register__title">{t.title}</span>
              {t.task_id && (
                <>
                  <OwnerSelect label={`Owner of ${t.title}`} value={t.owner_id} members={edits.members} nobody="No owner" onChange={(o) => edits.onTask(t.task_id!, { owner: o })} />
                  <input type="date" aria-label={`Date of ${t.title}`} value={t.due_date ?? ""} onChange={(e) => edits.onTask(t.task_id!, { due: e.target.value || null })} />
                  <select className="field-select" aria-label={`Status of ${t.title}`} value={t.status} onChange={(e) => edits.onTask(t.task_id!, { status: e.target.value })}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  {removing === t.task_id ? (
                    <span className="register__confirm">
                      <button type="button" className="link-btn link-btn--danger" onClick={() => { edits.onTask(t.task_id!, { remove: true }); setRemoving(null); }}>Remove</button>
                      <button type="button" className="link-btn" onClick={() => setRemoving(null)}>Keep</button>
                    </span>
                  ) : (
                    <button type="button" className="icon-btn" aria-label={`Remove ${t.title}`} onClick={() => setRemoving(t.task_id!)}><FontAwesomeIcon icon={faTrashCan} /></button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="form__actions"><button type="button" className="btn btn--soft" onClick={onClose}>Close</button></div>
    </Dialog>
  );
}

/** One click to close a task, one more to reopen it. */
export function DoneBox({ task, onTask }: { task: Task; onTask: (taskId: string, edit: TaskEdit) => void }) {
  const done = task.status === "done";
  return (
    <button
      type="button"
      className={`donebox${done ? " donebox--on" : ""}`}
      role="checkbox"
      aria-checked={done}
      aria-label={`${task.title}: done`}
      disabled={!task.task_id}
      onClick={() => task.task_id && onTask(task.task_id, { status: done ? "todo" : "done" })}
    >
      {done && <FontAwesomeIcon icon={faCheck} />}
    </button>
  );
}

/** The plan day by day: what is late, then each date with its milestones and tasks, then what has no date. */
export function AgendaDialog({ open, tasks, milestones, onClose, ...edits }: Edits & { open: boolean; tasks: Task[]; milestones: Milestone[]; onClose: () => void }) {
  const days = agenda(tasks, milestones, todayIso());
  return (
    <Dialog open={open} title="Day by day" onClose={onClose}>
      {days.length === 0 ? (
        <p className="muted register__empty">Nothing open. Tasks and milestones appear here on the day they are due.</p>
      ) : (
        <ol className="agenda">
          {days.map((d) => (
            <li key={d.key}>
              <h3 className={d.late ? "agenda__day agenda__day--late" : "agenda__day"}>{d.label}</h3>
              <ul>
                {d.milestones.map((m) => (
                  <li key={`m-${m.milestone_id ?? m.title}`} className="agenda__milestone"><FontAwesomeIcon icon={faFlag} /> {m.title}</li>
                ))}
                {d.tasks.map((t) => (
                  <li key={t.task_id ?? t.title} className="agenda__task">
                    <DoneBox task={t} onTask={edits.onTask} />
                    <span>{t.title}{d.late && t.due_date && <span className="muted small"> · was due {dayLabel(t.due_date)}</span>}</span>
                    <span className={t.owner_id ? "muted small" : "tag tag--warn"}>{t.owner_id ? edits.nameOf(t.owner_id) ?? "member" : "No owner"}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      <div className="form__actions"><button type="button" className="btn btn--soft" onClick={onClose}>Close</button></div>
    </Dialog>
  );
}
