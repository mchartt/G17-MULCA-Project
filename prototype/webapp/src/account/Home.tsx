import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState, type FormEvent } from "react";
import { joinMySpace, openMySpace, type SpaceRef, type User } from "../lib/account";
import { ApiError, saveToken } from "../lib/api";
import { faArrowRight, faRightFromBracket, faUserPen } from "../lib/icons";
import { codeInAddress } from "../lib/invite";
import { ProfileForm } from "./ProfileForm";
import { ProjectSetup } from "./ProjectSetup";

type Props = {
  user: User;
  spaces: SpaceRef[];
  disabled: boolean;
  onEnter: (spaceToken: string) => void;
  onUser: (user: User) => void;
  onLogout: () => void;
};

/** Every way in ends the same: a space token, saved, and the console opens. */
async function openWith(open: () => Promise<{ token: string }>, onEnter: (token: string) => void): Promise<string | null> {
  try {
    const { token } = await open();
    saveToken(token);
    onEnter(token);
    return null;
  } catch (err) {
    return err instanceof ApiError ? err.message : "Something went wrong. Try again.";
  }
}

/** Join a teammate's space with the invite code (filled in when you arrive from an invite link). */
export function JoinForm({ disabled, onEnter, title }: { disabled: boolean; onEnter: (token: string) => void; title?: string }) {
  const [code, setCode] = useState(codeInAddress);
  const invited = codeInAddress() !== "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const join = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(await openWith(() => joinMySpace(code), onEnter));
    setBusy(false);
  };
  return (
    <form className={`panel-card form${invited ? " form--invited" : ""}`} onSubmit={join}>
      <h3>{title ?? (invited ? "You are invited" : "Join with an invite code")}</h3>
      <label htmlFor="j-code">Invite code</label>
      <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="code-field" spellCheck={false} placeholder="AB12CD" />
      <p className="muted small">A teammate finds it in the room box of their space, at the bottom left.</p>
      {error && <p className="form__error" role="alert">{error}</p>}
      <button className={`btn ${invited ? "btn--primary" : "btn--dark"}`} type="submit" disabled={disabled || busy}>
        {busy ? "Joining…" : "Join the space"} <FontAwesomeIcon icon={faArrowRight} />
      </button>
    </form>
  );
}

/** A logged-in person's home: their spaces, a new space, an invite code, their profile. */
export function Home({ user, spaces, disabled, onEnter, onUser, onLogout }: Props) {
  const invited = codeInAddress() !== "";
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<{ where: number; text: string } | null>(null);
  const [editing, setEditing] = useState(false);

  async function open(id: number) {
    setBusy(id);
    setError(null);
    const text = await openWith(() => openMySpace(id), onEnter);
    if (text) setError({ where: id, text });
    setBusy(null);
  }

  const createForm = <ProjectSetup key="create" title="Start a new project" disabled={disabled} onEnter={onEnter} />;
  const joinForm = <JoinForm key="join" disabled={disabled} onEnter={onEnter} />;

  return (
    <div className="home">
      <div className="home__who">
        <p>Logged in as <strong>{user.displayName}</strong> <span className="muted">({user.email})</span></p>
        <div className="home__actions">
          <button className="btn btn--soft btn--small" aria-expanded={editing} onClick={() => setEditing(!editing)}><FontAwesomeIcon icon={faUserPen} /> My profile</button>
          <button className="btn btn--link" onClick={onLogout}><FontAwesomeIcon icon={faRightFromBracket} /> Log out</button>
        </div>
      </div>

      {editing && (
        <div className="panel-card home__profile">
          <h3>My profile</h3>
          <ProfileForm user={user} onSaved={onUser} onCancel={() => setEditing(false)} />
        </div>
      )}

      {spaces.length > 0 && (
        <div className="home__spaces">
          <h3>Your spaces</h3>
          <ul>
            {spaces.map((s) => (
              <li key={s.id} className="panel-card">
                <span><strong>{s.name}</strong> <code className="muted">{s.inviteCode}</code></span>
                <button className="btn btn--primary btn--small" disabled={disabled || busy !== null} onClick={() => void open(s.id)}>
                  {busy === s.id ? "Opening…" : "Open"} <FontAwesomeIcon icon={faArrowRight} />
                </button>
                {error?.where === s.id && <p className="form__error" role="alert">{error.text}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Arriving from an invite link, joining comes first. */}
      <div className="entry__forms">
        {invited ? <>{joinForm}{createForm}</> : <>{createForm}{joinForm}</>}
      </div>
    </div>
  );
}
