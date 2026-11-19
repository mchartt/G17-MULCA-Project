import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { DOCUMENT_TYPES } from "../lib/documents";
import { TagInput, withPending } from "./TagInput";

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

type KickoffProps = {
  open: boolean;
  onClose: () => void;
  onSend: (text: string) => Promise<string | null>;
  /** Reads the text of an uploaded document; absent where uploads are not available. */
  onRead?: (file: File) => Promise<{ name: string; text: string; truncated: boolean }>;
};

export function KickoffDialog({ open, onClose, onSend, onRead }: KickoffProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [source, setSource] = useState<string | null>(null);

  /** The document's text lands in the box, where the member can cut or correct it before sending. */
  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // the same file can be chosen again
    if (!file || !onRead) return;
    setReading(true);
    setError(null);
    try {
      const read = await onRead(file);
      setText((before) => (before.trim() ? `${before.trim()}\n\n${read.text}` : read.text));
      setSource(read.truncated ? `${read.name} (only the first part: the document is long)` : read.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The file could not be read.");
    } finally {
      setReading(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(await onSend(text));
    setBusy(false);
  }

  return (
    <Dialog open={open} title="Start from the assignment" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <p className="muted">Upload the assignment or paste its text. Cadence lists deliverables and deadlines and proposes a goal as a card. Nothing is saved until a member confirms it.</p>
        {onRead && (
          <div className="upload">
            <label className="btn btn--soft btn--small" htmlFor="kickoff-file">{reading ? "Reading the document…" : "Upload a document"}</label>
            <input id="kickoff-file" className="sr-only" type="file" accept={DOCUMENT_TYPES} onChange={(e) => void upload(e)} disabled={reading} />
            <span className="muted small">{source ? `Read from ${source}. You can edit the text below.` : "PDF, Word, PowerPoint or text, up to 10 MB. The file is not kept."}</span>
          </div>
        )}
        <label htmlFor="kickoff-text">Assignment</label>
        <textarea id="kickoff-text" className="kickoff__text" rows={8} value={text} onChange={(e) => setText(e.target.value)} required />
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--primary" disabled={busy || !text.trim()}>{busy ? "Cadence is reading…" : "Send to Cadence"}</button>
        </div>
      </form>
    </Dialog>
  );
}

export type Profile = { discipline: string; skills: string[]; weekly_hours: number; background: string };

export function ProfileDialog({ open, onClose, onSave }: { open: boolean; onClose: () => void; onSave: (p: Profile) => Promise<string | null> }) {
  const [profile, setProfile] = useState<Profile>({ discipline: "", skills: [], weekly_hours: 6, background: "" });
  const [pending, setPending] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSave({ ...profile, skills: withPending(profile.skills, pending) });
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
        <label htmlFor="p-skills">Skills (press Enter after each)</label>
        <TagInput id="p-skills" tags={profile.skills} onChange={(skills) => setProfile({ ...profile, skills })} onPending={setPending} placeholder="User research, prototyping" />
        <label htmlFor="p-background">Background, in your own words</label>
        <textarea id="p-background" rows={3} maxLength={600} value={profile.background} onChange={(e) => setProfile({ ...profile, background: e.target.value })} placeholder="What you study, what you have done before, what you would like to work on." />
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

/**
 * How to bring Cadence into the group's Discord server or Slack workspace.
 * Honest about the condition: it works only where the Cadence bot is installed.
 */
export function ConnectDialog({ open, code, onClose }: { open: boolean; code: string; onClose: () => void }) {
  const command = `/coordinator link ${code}`;
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the command stays on screen to copy by hand */
    }
  };
  return (
    <Dialog open={open} title="Connect Slack or Discord" onClose={onClose}>
      <div className="connect">
        <p className="muted">Keep talking where your group already talks. Cadence reads the linked channel too, and the plan, the decisions and the cards are the same everywhere.</p>
        <ol className="connect__steps">
          <li>
            <strong>Install the Cadence bot</strong>
            <span className="muted small">Whoever manages your Discord server or Slack workspace adds the bot once. Ask your team who has the invite link of the bot.</span>
          </li>
          <li>
            <strong>Link the channel to this space</strong>
            <span className="muted small">In the channel where the group talks, write:</span>
            <span className="connect__command"><code>{command}</code><button type="button" className="btn btn--soft btn--small" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button></span>
          </li>
          <li>
            <strong>Talk as usual</strong>
            <span className="muted small">Messages from the channel show here with a Discord or Slack tag, and Cadence's cards show there too.</span>
          </li>
        </ol>
        <p className="muted small">Without the bot installed, the command does nothing. Nothing is shared until a channel is linked.</p>
        <div className="form__actions">
          <button type="button" className="btn btn--primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </Dialog>
  );
}
