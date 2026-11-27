import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { DOCUMENT_TYPES } from "../lib/documents";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faFileLines, faPlug, faPlus, faTrashCan, faUserPen } from "../lib/icons";
import type { MemberId, ProjectDocument } from "../lib/types";
import { connectOptions, type ConnectOptions } from "../lib/api";
import { initials } from "./Chat";
import { profileFacts, type MemberProfile } from "./space";
import { TagInput, withPending } from "./TagInput";

/** The language Cadence writes in for a group: "" means it follows the chat. */
export const LANGUAGES = [
  { value: "", label: "Follow the chat" },
  { value: "en", label: "English" },
  { value: "it", label: "Italiano" },
];

/**
 * A member rewrites the goal and the deliverables. Saving does not change the
 * plan: it posts a charter card in the chat, saved when a member confirms it.
 */
export function GoalForm({ goal, deliverables, onSave, onClose }: { goal: string; deliverables: string[]; onSave: (goal: string, deliverables: string[]) => Promise<string | null>; onClose: () => void }) {
  const [text, setText] = useState(goal);
  const [list, setList] = useState(deliverables.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSave(text.trim(), list.split("\n").map((d) => d.trim()).filter(Boolean));
    setBusy(false);
    setError(result);
    if (!result) onClose();
  }

  return (
    <form className="form goalform" onSubmit={submit}>
      <label htmlFor="goal-text">Goal</label>
      <textarea id="goal-text" rows={5} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} required />
      <label htmlFor="goal-deliverables">Deliverables, one per line</label>
      <textarea id="goal-deliverables" rows={3} value={list} onChange={(e) => setList(e.target.value)} />
      <p className="muted small">Your change becomes a card in the chat. It is saved when a member confirms it.</p>
      {error && <p className="form__error" role="alert">{error}</p>}
      <div className="form__actions">
        <button type="button" className="btn btn--soft btn--small" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn btn--primary btn--small" disabled={busy || !text.trim()}>{busy ? "Sending…" : "Propose change"}</button>
      </div>
    </form>
  );
}

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
 * How to bring Cadence into the group's Discord server or Slack workspace, for
 * someone who never set up a bot (DECISIONS.md, 27/11): pick where the group
 * talks, press "Add Cadence to …", paste the space's link in the channel.
 * Voice is one click in Discord after that. Honest when this server has no
 * Discord or Slack app set up (connect_routes.py answers null).
 */
type Place = "discord" | "slack";
const PLACE_NAMES: Record<Place, string> = { discord: "Discord", slack: "Slack" };

export function ConnectDialog({ open, code, onClose, onPersonalCode }: { open: boolean; code: string; onClose: () => void; onPersonalCode?: () => Promise<string> }) {
  const command = `/coordinator link ${code}`;
  // The easiest way: the space's invite link, pasted in the channel, links it (mulca_discord/invites.py).
  const inviteLink = `${location.origin}/join/${code}`;
  const [place, setPlace] = useState<Place>("discord");
  const [options, setOptions] = useState<ConnectOptions | null>(null);
  const [copied, setCopied] = useState(false);
  // "Be yourself there": the server's answer to the "me" command, shown as it is
  // when it holds no code (a refusal), else as the command to write in the channel.
  const [mine, setMine] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const meCommand = mine?.match(/\/coordinator me [A-Z0-9]+/)?.[0] ?? null;
  useEffect(() => {
    if (!open) {
      setMine(null); // a code is shown once: the next visit asks for a new one
      return;
    }
    let live = true;
    void connectOptions().then((found) => live && setOptions(found));
    return () => {
      live = false;
    };
  }, [open]);
  const personal = async () => {
    if (!onPersonalCode) return;
    setAsking(true);
    setMine(await onPersonalCode());
    setAsking(false);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the link stays on screen to copy by hand */
    }
  };
  const name = PLACE_NAMES[place];
  const install = options?.[place] ?? null;
  return (
    <Dialog open={open} title="Connect Slack or Discord" onClose={onClose}>
      <div className="connect">
        <p className="muted">Keep talking where your group already talks. The plan, the decisions and the cards are the same here and there.</p>
        <div className="seg connect__places" role="radiogroup" aria-label="Where does your group talk?">
          {(Object.keys(PLACE_NAMES) as Place[]).map((key) => (
            <button key={key} type="button" role="radio" aria-checked={place === key} className="seg__item" onClick={() => setPlace(key)}>
              {PLACE_NAMES[key]}
            </button>
          ))}
        </div>
        <ol className="connect__steps">
          <li>
            <strong>Add Cadence to {name}</strong>
            {install ? (
              <>
                <span className="muted small">
                  {place === "discord"
                    ? "Pick your group's server and press Authorize. You need to be allowed to manage that server."
                    : <>Pick your group's workspace and press Allow. Then, in the channel where your group talks, write <code>/invite @Cadence</code>.</>}
                </span>
                <a className="btn btn--primary btn--small connect__add" href={install} target="_blank" rel="noopener noreferrer">
                  <FontAwesomeIcon icon={faPlug} /> Add Cadence to {name}
                </a>
              </>
            ) : (
              <span className="muted small">
                {options === null ? "Checking…" : `${name} is not turned on for this Cadence server yet. If Cadence is already in your ${place === "discord" ? "server" : "workspace"}, go to step 2.`}
              </span>
            )}
          </li>
          <li>
            <strong>Paste this link in your group's channel</strong>
            <span className="connect__command"><code>{inviteLink}</code><button type="button" className="btn btn--soft btn--small" onClick={() => void copy()}>{copied ? "Copied" : "Copy link"}</button></span>
            <span className="muted small">Cadence answers there when the channel is linked. That's it: talk as usual.</span>
          </li>
          <li>
            <strong>Voice calls</strong>
            <span className="muted small">
              {place === "discord"
                ? "Right after the link, Cadence asks in the channel whether to listen to your calls: one click on the voice channel you use. It keeps the transcript and speaks only when called by name."
                : "Cadence cannot join Slack huddles. For voice calls, use Discord."}
            </span>
          </li>
        </ol>
        <details className="connect__more">
          <summary>Optional: be yourself there</summary>
          <p className="muted small">So your tasks and profile follow you: get your personal code and write it once in that channel. It works once and for 15 minutes. Never share it: whoever uses it acts as you.</p>
          {meCommand ? (
            <span className="connect__command"><code>{meCommand}</code></span>
          ) : (
            onPersonalCode && <button type="button" className="btn btn--soft btn--small" disabled={asking} onClick={() => void personal()}>{asking ? "Asking…" : "Get my personal code"}</button>
          )}
          {mine && !meCommand && <span className="form__error" role="alert">{mine}</span>}
          <p className="muted small">Instead of the link you can also write <code>{command}</code>.</p>
        </details>
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Done</button>
        </div>
      </div>
    </Dialog>
  );
}


const size = (chars: number) => (chars < 1000 ? `${chars} characters` : `${Math.round(chars / 100) / 10}k characters`);
const added = (unix: number) => new Date(unix * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/**
 * Project settings > Documents: what Cadence reads when it answers (the
 * assignment, notes, the setup desk's description). A file is read once and
 * only its text is kept; removing it means Cadence no longer reads it.
 */
function DocumentsSection({ documents, onAdd, onRemove }: { documents: ProjectDocument[]; onAdd: (file: File) => Promise<string | null>; onRemove: (id: string) => Promise<string | null> }) {
  const picker = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    for (const file of Array.from(files)) {
      setBusy(`Reading ${file.name}…`);
      const problem = await onAdd(file);
      if (problem) {
        setError(`${file.name}: ${problem}`);
        break;
      }
    }
    setBusy(null);
  }

  async function remove(id: string) {
    setBusy("Removing…");
    setError(await onRemove(id));
    setConfirming(null);
    setBusy(null);
  }

  return (
    <section className="settings__section" aria-labelledby="settings-docs">
      <h3 id="settings-docs">Documents Cadence reads</h3>
      <p className="muted small">Cadence reads their text when it answers your questions. Files are read once; only their text is kept, until you remove it.</p>
      {documents.length === 0 ? (
        <p className="muted small">No documents yet.</p>
      ) : (
        <ul className="docs-list" aria-label="Documents">
          {documents.map((d) => (
            <li key={d.document_id} className="docs-list__item">
              <FontAwesomeIcon icon={faFileLines} aria-hidden="true" />
              <span className="docs-list__name" title={d.name}>{d.name}</span>
              <span className="muted small">{size(d.chars)} · {added(d.added_at)}</span>
              {confirming === d.document_id ? (
                <span className="docs-list__confirm">
                  <button type="button" className="btn btn--soft btn--small" onClick={() => setConfirming(null)}>Keep</button>
                  <button type="button" className="btn btn--danger btn--small" disabled={busy !== null} onClick={() => void remove(d.document_id)}>Remove</button>
                </span>
              ) : (
                <button type="button" className="link-btn" aria-label={`Remove ${d.name}`} onClick={() => setConfirming(d.document_id)}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="btn btn--soft btn--small" disabled={busy !== null} onClick={() => picker.current?.click()}>
        <FontAwesomeIcon icon={faPlus} /> Add a document
      </button>
      <input ref={picker} className="sr-only" type="file" multiple accept={DOCUMENT_TYPES} tabIndex={-1} aria-hidden="true" onChange={(e) => { void add(e.target.files); e.target.value = ""; }} />
      {busy && <p className="muted small" role="status">{busy}</p>}
      {error && <p className="form__error" role="alert">{error}</p>}
    </section>
  );
}

type SettingsProps = {
  open: boolean;
  name: string;
  goal: string;
  deliverables: string[];
  language: string;
  /** The documents Cadence reads as context (Matteo, 20/11: editable from the settings). */
  documents: ProjectDocument[];
  onAddDocument: (file: File) => Promise<string | null>;
  onRemoveDocument: (documentId: string) => Promise<string | null>;
  onRename: (name: string) => Promise<string | null>;
  onCharter: (goal: string, deliverables: string[]) => Promise<string | null>;
  onLanguage: (language: string) => void;
  onConnect: () => void;
  onDelete: () => void;
  onClose: () => void;
};

/**
 * Project settings, behind the gear next to the space's name. Renaming is a
 * member's own action (saved at once); the goal and deliverables change the
 * plan, so they become a card the group confirms, like every plan change.
 */
export function ProjectSettingsDialog({ open, name, goal, deliverables, language, documents, onAddDocument, onRemoveDocument, onRename, onCharter, onLanguage, onConnect, onDelete, onClose }: SettingsProps) {
  const [draft, setDraft] = useState(name);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);

  // Each opening starts from the space as it is now (a rename arriving while open keeps the message).
  useEffect(() => {
    if (open) {
      setDraft(name);
      setMessage(null);
      setEditingGoal(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function rename(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const problem = await onRename(draft);
    setBusy(false);
    setMessage(problem ? { ok: false, text: problem } : { ok: true, text: "Name saved." });
  }

  return (
    <Dialog open={open} title="Project settings" onClose={onClose}>
      {/* Rendered only while open, so its fields never duplicate the labels of the page behind. */}
      {open && <div className="settings">
        <form className="form settings__section" onSubmit={rename}>
          <label htmlFor="settings-name">Name of the space</label>
          <div className="settings__row">
            <input id="settings-name" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={80} required />
            <button type="submit" className="btn btn--primary btn--small" disabled={busy || !draft.trim() || draft.trim() === name}>{busy ? "Saving…" : "Save name"}</button>
          </div>
          {message && <p className={message.ok ? "form__ok" : "form__error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
        </form>

        <section className="settings__section" aria-labelledby="settings-goal">
          <h3 id="settings-goal">Goal and deliverables</h3>
          {editingGoal ? (
            <GoalForm goal={goal} deliverables={deliverables} onSave={onCharter} onClose={() => setEditingGoal(false)} />
          ) : (
            <>
              <p className={goal ? "settings__goal" : "muted"}>{goal || "No goal yet. Paste the brief, or write it here."}</p>
              {deliverables.length > 0 && <ul className="panel__list">{deliverables.map((d) => <li key={d}>{d}</li>)}</ul>}
              <button type="button" className="btn btn--soft btn--small" onClick={() => setEditingGoal(true)}>{goal ? "Edit goal" : "Write the goal"}</button>
              <p className="muted small">A change becomes a card in the chat. It is saved when a member confirms it.</p>
            </>
          )}
        </section>

        <DocumentsSection documents={documents} onAdd={onAddDocument} onRemove={onRemoveDocument} />

        <section className="settings__section settings__inline">
          <label htmlFor="settings-language-select">Cadence writes in</label>
          <select id="settings-language-select" className="tasks__status" value={language} onChange={(e) => onLanguage(e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </section>

        <section className="settings__section settings__inline">
          <span>Slack and Discord</span>
          <button type="button" className="btn btn--soft btn--small" onClick={onConnect}><FontAwesomeIcon icon={faPlug} /> Connect a channel</button>
        </section>

        <section className="settings__section settings__danger" aria-labelledby="settings-danger">
          <h3 id="settings-danger">Delete the space</h3>
          <p className="muted small">Messages, plan and decisions are deleted for everyone. This cannot be undone.</p>
          <button type="button" className="btn btn--link btn--danger" onClick={onDelete}><FontAwesomeIcon icon={faTrashCan} /> Delete this space</button>
        </section>

        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={onClose}>Close</button>
        </div>
      </div>}
    </Dialog>
  );
}

type MemberProps = {
  open: boolean;
  member: { id: MemberId; name: string } | null;
  profile: MemberProfile | undefined;
  color: string;
  isMe: boolean;
  onEditProfile: () => void;
  onClose: () => void;
};

/** A teammate's profile, from the sidebar: what they wrote about themselves, nothing computed about them. */
export function MemberDialog({ open, member, profile, color, isMe, onEditProfile, onClose }: MemberProps) {
  const facts = profileFacts(profile);
  const skills = profile?.skills ?? [];
  return (
    <Dialog open={open} title={member ? (isMe ? `${member.name} (you)` : member.name) : "Member"} onClose={onClose}>
      {open && member && (
        <div className="member">
          <div className="member__head">
            <span className="avatar member__avatar" style={{ background: color }} aria-hidden="true">{initials(member.name)}</span>
            <p className="muted">{profile?.discipline?.trim() || (facts.length ? "" : "No profile yet.")}</p>
          </div>
          {skills.length > 0 && (
            <ul className="member__skills" aria-label="Skills">{skills.map((s) => <li key={s} className="tag">{s}</li>)}</ul>
          )}
          {typeof profile?.weekly_hours === "number" && <p><strong>{profile.weekly_hours} h</strong> a week for group projects</p>}
          {profile?.background?.trim() && <p className="member__background">{profile.background}</p>}
          <p className="muted small">Cadence uses this only to suggest who could take a task. No scores, no rankings.</p>
          <div className="form__actions">
            {isMe && <button type="button" className="btn btn--soft" onClick={onEditProfile}><FontAwesomeIcon icon={faUserPen} /> Edit my profile</button>}
            <button type="button" className="btn btn--primary" onClick={onClose}>Close</button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
