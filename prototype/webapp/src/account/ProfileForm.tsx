import { useState, type FormEvent } from "react";
import { saveProfile, type User } from "../lib/account";
import { ApiError } from "../lib/api";
import { TagInput, withPending } from "../console/TagInput";

type Props = { user: User; onSaved: (user: User) => void; onCancel?: () => void };

/**
 * The profile of the person, saved once in the account and sent to the
 * coordinator of every space they are in. Used on the home page and in the
 * console ("Edit my profile").
 */
export function ProfileForm({ user, onSaved, onCancel }: Props) {
  const [name, setName] = useState(user.displayName);
  const [discipline, setDiscipline] = useState(user.discipline);
  const [skills, setSkills] = useState(user.skills);
  const [pending, setPending] = useState("");
  const [background, setBackground] = useState(user.background ?? "");
  const [hours, setHours] = useState(user.weeklyHours === null ? "" : String(user.weeklyHours));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const saved = await saveProfile({
        displayName: name,
        discipline,
        skills: withPending(skills, pending),
        weeklyHours: hours === "" ? null : Number(hours),
        background,
      });
      setMessage({ ok: true, text: "Profile saved. Your spaces see the new one." });
      onSaved(saved);
    } catch (err) {
      setMessage({ ok: false, text: err instanceof ApiError ? err.message : "Profile not saved. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <p className="muted">Cadence uses this only to suggest who could take a task. No scores, no rankings.</p>
      <label htmlFor="p-name">Name</label>
      <input id="p-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required />
      <label htmlFor="p-discipline">Discipline</label>
      <input id="p-discipline" value={discipline} onChange={(e) => setDiscipline(e.target.value)} maxLength={100} placeholder="Interaction design" />
      <label htmlFor="p-skills">Skills (press Enter after each)</label>
      <TagInput id="p-skills" tags={skills} onChange={setSkills} onPending={setPending} placeholder="User research, prototyping" />
      <label htmlFor="p-background">Background, in your own words</label>
      <textarea id="p-background" rows={3} maxLength={600} value={background} onChange={(e) => setBackground(e.target.value)} placeholder="What you study, what you have done before, what you would like to work on." />
      <label htmlFor="p-hours">Hours per week for group projects</label>
      <input id="p-hours" type="number" min={0} max={80} value={hours} onChange={(e) => setHours(e.target.value)} />
      {message && <p className={message.ok ? "form__ok" : "form__error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
      <div className="form__actions">
        {onCancel && <button type="button" className="btn btn--soft" onClick={onCancel}>Close</button>}
        <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
      </div>
    </form>
  );
}
