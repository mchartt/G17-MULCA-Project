import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

/** The shared modal: a native <dialog> with its title wired for screen readers. */
export function Dialog({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog ref={ref} className="dialog" aria-labelledby={titleId} onClose={onClose}>
      <h2 id={titleId}>{title}</h2>
      {children}
    </dialog>
  );
}

export function KickoffDialog({ open, onClose, onSend }: { open: boolean; onClose: () => void; onSend: (text: string) => Promise<string | null> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(await onSend(text));
    setBusy(false);
  }

  return (
    <Dialog open={open} title="Start from the assignment" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">Paste the assignment text. Cadence lists deliverables and deadlines and proposes a goal as a card. Nothing is saved until a member confirms it.</p>
        <label htmlFor="kickoff-text">Assignment</label>
        <textarea id="kickoff-text" rows={10} value={text} onChange={(e) => setText(e.target.value)} required />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={busy || !text.trim()}>{busy ? "Cadence is reading…" : "Send to Cadence"}</button>
        </div>
      </form>
    </Dialog>
  );
}

export type Profile = { discipline: string; skills: string; weekly_hours: number };

export function ProfileDialog({ open, onClose, onSave }: { open: boolean; onClose: () => void; onSave: (p: Profile) => Promise<string | null> }) {
  const [profile, setProfile] = useState<Profile>({ discipline: "", skills: "", weekly_hours: 6 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSave(profile);
    setBusy(false);
    if (result) setError(result);
    else onClose();
  }

  return (
    <Dialog open={open} title="Your profile" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">Cadence uses this only to suggest who could take a task. No scores, no rankings.</p>
        <label htmlFor="p-discipline">Discipline</label>
        <input id="p-discipline" value={profile.discipline} onChange={(e) => setProfile({ ...profile, discipline: e.target.value })} placeholder="Interaction design" required />
        <label htmlFor="p-skills">Skills</label>
        <input id="p-skills" value={profile.skills} onChange={(e) => setProfile({ ...profile, skills: e.target.value })} placeholder="User research, prototyping" />
        <label htmlFor="p-hours">Hours per week for this project</label>
        <input id="p-hours" type="number" min={0} max={80} value={profile.weekly_hours} onChange={(e) => setProfile({ ...profile, weekly_hours: Number(e.target.value) })} />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
        </div>
      </form>
    </Dialog>
  );
}

/** Rule 10: delete every piece of the group's data, after typing the space's name. */
export function DeleteDialog({ open, spaceName, onClose, onDelete }: { open: boolean; spaceName: string; onClose: () => void; onDelete: (confirm: string) => Promise<string | null> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(await onDelete(text));
    setBusy(false);
  }

  return (
    <Dialog open={open} title="Delete this space" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">This deletes the chat, the plan, the decisions, the profiles and Cadence's memory of this group, for every member. It cannot be undone.</p>
        <label htmlFor="delete-confirm">Type <strong>{spaceName}</strong> to confirm</label>
        <input id="delete-confirm" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" required />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--danger" disabled={busy || text.trim().toLowerCase() !== spaceName.trim().toLowerCase()}>{busy ? "Deleting…" : "Delete everything"}</button>
        </div>
      </form>
    </Dialog>
  );
}

/** M4 /planning: the members write the tasks; Cadence suggests owners on a card. */
export function PlanningDialog({ open, onClose, onSend }: { open: boolean; onClose: () => void; onSend: (text: string) => Promise<string | null> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSend(text);
    setBusy(false);
    setError(result);
    if (!result) setText("");
  }

  return (
    <Dialog open={open} title="Plan the work together" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">Write the tasks the group agreed on, one per line. Cadence suggests who could take each one, with a reason, from your profiles. Nothing is saved until a member confirms the card.</p>
        <label htmlFor="planning-text">Tasks</label>
        <textarea id="planning-text" rows={8} value={text} onChange={(e) => setText(e.target.value)} required placeholder={"Server API\nUI screens\nUser test with 5 people"} />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={busy || !text.trim()}>{busy ? "Cadence is planning…" : "Suggest owners"}</button>
        </div>
      </form>
    </Dialog>
  );
}
