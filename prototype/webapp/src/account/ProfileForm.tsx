import { useState, type FormEvent } from "react";
import { saveProfile, type User } from "../lib/account";
import { ApiError } from "../lib/api";

type Props = { user: User; onSaved: (user: User) => void; onCancel?: () => void };

/**
 * The profile of the person, saved once in the account and sent to the
 * coordinator of every space they are in. Used on the home page and in the
 * console ("Edit my profile").
 */
export function ProfileForm({ user, onSaved, onCancel }: Props) {
  const [name, setName] = useState(user.displayName);
  const [discipline, setDiscipline] = useState(user.discipline);
  const [skills, setSkills] = useState(user.skills.join(", "));
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
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        weeklyHours: hours === "" ? null : Number(hours),
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
      <label htmlFor="p-skills">Skills, separated by commas</label>
      <input id="p-skills" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="User research, prototyping" />
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
